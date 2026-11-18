package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

const (
	maxArchiveRequestBytes = 64 << 10
	maxUpstreamBodyBytes   = 1 << 20
)

type archiveHandler struct {
	baseURL *url.URL
	client  *http.Client
}

func newArchiveHandler(base *url.URL, timeout time.Duration) *archiveHandler {
	return &archiveHandler{
		baseURL: base,
		client: &http.Client{
			Timeout: timeout,
			CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
				return http.ErrUseLastResponse
			},
			Transport: &http.Transport{
				Proxy:                 http.ProxyFromEnvironment,
				MaxIdleConns:          32,
				MaxIdleConnsPerHost:   16,
				IdleConnTimeout:       90 * time.Second,
				ResponseHeaderTimeout: timeout,
			},
		},
	}
}

type archiveRequest struct {
	SeedURL        string   `json:"seedUrl"`
	CollectionID   string   `json:"collectionId,omitempty"`
	MaxDepth       *int     `json:"maxDepth"`
	MaxPages       *int     `json:"maxPages"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}

type archiveAccepted struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	StatusURL string `json:"statusUrl"`
}

func (h *archiveHandler) create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get("Idempotency-Key")
	if len(key) < 8 || len(key) > 200 || strings.TrimSpace(key) != key {
		writeProblem(w, r, http.StatusBadRequest, "idempotency-key", "Invalid Idempotency Key", "Idempotency-Key must contain 8 to 200 non-whitespace-bounded characters.")
		return
	}
	contentType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || contentType != "application/json" {
		writeProblem(w, r, http.StatusUnsupportedMediaType, "content-type", "Unsupported Media Type", "Expected application/json.")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxArchiveRequestBytes)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	var payload archiveRequest
	if err := decoder.Decode(&payload); err != nil {
		writeProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected a valid JSON archive request within the size limit.")
		return
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		writeProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected one JSON object.")
		return
	}
	if err := validateArchive(payload); err != nil {
		writeProblem(w, r, http.StatusUnprocessableEntity, "invalid-archive", "Invalid Archive", err.Error())
		return
	}

	// Preserve the original JSON and key: Coordinator owns canonicalization and
	// durable idempotency; the Gateway must not invent an admission fingerprint.
	// Re-encoding the decoded payload is safe for semantic JSON equivalence, but
	// preserving input bytes avoids accidental omission of explicitly set fields.
	// The body is decoded above for validation; marshal the parsed representation.
	body, err := json.Marshal(payload)
	if err != nil {
		writeProblem(w, r, http.StatusInternalServerError, "internal", "Internal Server Error", "Unable to encode archive request.")
		return
	}
	upstream, err := h.request(r.Context(), http.MethodPost, "/archives", bytes.NewReader(body))
	if err != nil {
		writeProblem(w, r, http.StatusServiceUnavailable, "coordinator-unavailable", "Coordinator Unavailable", "Admission could not be confirmed. Retry with the same Idempotency-Key.")
		return
	}
	upstream.Header.Set("Content-Type", "application/json")
	upstream.Header.Set("Idempotency-Key", key)
	response, data, err := h.exchange(upstream)
	if err != nil {
		writeProblem(w, r, http.StatusServiceUnavailable, "coordinator-unavailable", "Coordinator Unavailable", "Admission could not be confirmed. Retry with the same Idempotency-Key.")
		return
	}
	if response.StatusCode != http.StatusAccepted {
		h.forwardFailure(w, r, response.StatusCode, data)
		return
	}

	var accepted archiveAccepted
	if err := json.Unmarshal(data, &accepted); err != nil || accepted.Status != "ACCEPTED" || !validArchiveID(accepted.ArchiveID) {
		writeProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Coordinator returned an invalid admission response.")
		return
	}
	accepted.StatusURL = "/archives/" + url.PathEscape(accepted.ArchiveID)
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Location", accepted.StatusURL)
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(accepted)
}

func (h *archiveHandler) status(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "archiveId")
	if !validArchiveID(id) {
		writeProblem(w, r, http.StatusBadRequest, "invalid-archive-id", "Invalid Archive ID", "Archive ID must be a nonempty path segment.")
		return
	}
	upstream, err := h.request(r.Context(), http.MethodGet, "/archives/"+url.PathEscape(id), nil)
	if err != nil {
		writeProblem(w, r, http.StatusServiceUnavailable, "coordinator-unavailable", "Coordinator Unavailable", "Archive status is temporarily unavailable.")
		return
	}
	response, data, err := h.exchange(upstream)
	if err != nil {
		writeProblem(w, r, http.StatusServiceUnavailable, "coordinator-unavailable", "Coordinator Unavailable", "Archive status is temporarily unavailable.")
		return
	}
	if response.StatusCode != http.StatusOK {
		h.forwardFailure(w, r, response.StatusCode, data)
		return
	}
	var status struct {
		ArchiveID string          `json:"archiveId"`
		Status    string          `json:"status"`
		Capture   json.RawMessage `json:"capture"`
		Replay    json.RawMessage `json:"replay"`
		Search    json.RawMessage `json:"search"`
	}
	if err := json.Unmarshal(data, &status); err != nil || status.ArchiveID != id ||
		status.Status == "" || len(status.Capture) == 0 || len(status.Replay) == 0 || len(status.Search) == 0 {
		writeProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Coordinator returned an invalid archive status.")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

func (h *archiveHandler) request(ctx context.Context, method, path string, body io.Reader) (*http.Request, error) {
	target := *h.baseURL
	target.Path = path
	target.RawPath = ""
	return http.NewRequestWithContext(ctx, method, target.String(), body)
}

func (h *archiveHandler) exchange(request *http.Request) (*http.Response, []byte, error) {
	response, err := h.client.Do(request)
	if err != nil {
		return nil, nil, fmt.Errorf("coordinator HTTP request: %w", err)
	}
	defer response.Body.Close()

	data, err := io.ReadAll(io.LimitReader(response.Body, maxUpstreamBodyBytes+1))
	if err != nil {
		return nil, nil, fmt.Errorf("read coordinator HTTP response: %w", err)
	}
	if len(data) > maxUpstreamBodyBytes {
		return nil, nil, errors.New("coordinator response exceeds limit")
	}
	return response, data, nil
}

func (h *archiveHandler) forwardFailure(w http.ResponseWriter, r *http.Request, status int, data []byte) {
	if status == http.StatusBadRequest || status == http.StatusConflict || status == http.StatusUnprocessableEntity ||
		status == http.StatusNotFound || status == http.StatusServiceUnavailable {
		var upstream problem
		if err := json.Unmarshal(data, &upstream); err == nil && upstream.Status == status &&
			upstream.Title != "" && upstream.Type != "" {
			writeProblem(w, r, status, upstreamProblemKind(status), upstream.Title, upstream.Detail)
			return
		}
	}
	writeProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Coordinator returned an unsupported or malformed response.")
}

func upstreamProblemKind(status int) string {
	switch status {
	case http.StatusBadRequest:
		return "coordinator-bad-request"
	case http.StatusConflict:
		return "conflict"
	case http.StatusUnprocessableEntity:
		return "coordinator-validation"
	case http.StatusNotFound:
		return "not-found"
	default:
		return "coordinator-unavailable"
	}
}

func validateArchive(req archiveRequest) error {
	if !validHTTPURL(req.SeedURL) {
		return errors.New("seedUrl must be an absolute HTTP(S) URL without credentials or fragment")
	}
	if req.MaxDepth == nil || *req.MaxDepth < 0 {
		return errors.New("maxDepth must be an integer greater than or equal to zero")
	}
	if req.MaxPages == nil || *req.MaxPages < 1 {
		return errors.New("maxPages must be an integer greater than or equal to one")
	}
	if req.AuthGeneration != nil && *req.AuthGeneration < 1 {
		return errors.New("authGeneration must be positive")
	}
	seen := make(map[string]struct{}, len(req.AllowedOrigins))
	for _, origin := range req.AllowedOrigins {
		if !validHTTPURL(origin) {
			return errors.New("allowedOrigins entries must be absolute HTTP(S) URLs without credentials or fragment")
		}
		if _, duplicate := seen[origin]; duplicate {
			return errors.New("allowedOrigins entries must be unique")
		}
		seen[origin] = struct{}{}
	}
	return nil
}

func validHTTPURL(raw string) bool {
	parsed, err := url.Parse(raw)
	return err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") &&
		parsed.Hostname() != "" && parsed.User == nil && parsed.Fragment == ""
}

func validArchiveID(id string) bool {
	return id != "" && id != "." && id != ".." && !strings.ContainsAny(id, "/\\")
}
