// Package sessionapi provides HTTP handlers for the Sessions API
package sessionapi

import (
	"encoding/json"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/common"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

type Handler struct {
	client *upstream.Client
}

type createRequest struct {
	ArchiveID string `json:"archiveId"`
	TargetURL string `json:"targetUrl"`
}

type updateRequest struct {
	Status string `json:"status"`
}

type sessionResponse struct {
	SessionID string `json:"sessionId"`
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	ExpiresAt string `json:"expiresAt"`
}

func NewHandler(client *upstream.Client) Handler {
	return Handler{client: client}
}

func (h Handler) Create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get(httpx.IdempotencyHeader)

	if !httpx.ValidIdempotencyKey(key) {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-idempotency-key",
			"Invalid Idempotency Key",
			"Idempotency-Key is required and must contain 8 to 200 characters.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	var input createRequest
	raw, err := httpx.DecodeJSONBytes(w, r, &input)

	if err != nil {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			err.Error(),
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	if !httpx.ValidPathSegment(input.ArchiveID) || !httpx.ValidHTTPURL(input.TargetURL) {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			"Expected archiveId and absolute HTTP(S) targetUrl.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	result, err := h.client.JSON(r.Context(), http.MethodPost, common.SessionsPath, "", key, raw)

	if err != nil {
		common.UpstreamError(w, r, err, "Capture")
		return
	}

	if result.Status != http.StatusCreated {
		common.ForwardJSON(w, r, result, http.StatusCreated, "Capture")
		return
	}

	var created sessionResponse
	decodeErr := json.Unmarshal(result.Body, &created)
	validSession := httpx.ValidPathSegment(created.SessionID) && created.ArchiveID == input.ArchiveID &&
		created.Status != "" && created.ExpiresAt != ""

	if decodeErr != nil || !validSession {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadGateway,
			"invalid-upstream",
			"Invalid Upstream Response",
			"Capture returned invalid session metadata.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	location := common.SessionPathPrefix + url.PathEscape(created.SessionID)

	w.Header().Set(httpx.LocationHeader, location)
	common.ForwardJSON(w, r, result, http.StatusCreated, "Capture")
}

func (h Handler) Get(w http.ResponseWriter, r *http.Request) {
	h.forward(w, r, http.MethodGet, nil)
}

func (h Handler) Update(w http.ResponseWriter, r *http.Request) {
	var input updateRequest
	raw, err := httpx.DecodeJSONBytes(w, r, &input)

	if err != nil {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			err.Error(),
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	validStatus := input.Status == "COMPLETED" || input.Status == "CANCELLED"

	if !validStatus {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			"status must be COMPLETED or CANCELLED.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	h.forward(w, r, http.MethodPut, raw)
}

func (h Handler) forward(w http.ResponseWriter, r *http.Request, method string, body []byte) {
	id := chi.URLParam(r, common.SessionIDParameter)

	if !httpx.ValidPathSegment(id) {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session-id",
			"Invalid Session ID",
			"Invalid session ID.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	path := common.SessionPathPrefix + url.PathEscape(id)
	result, err := h.client.JSON(r.Context(), method, path, "", "", body)

	if err != nil {
		common.UpstreamError(w, r, err, "Capture")
		return
	}

	if result.Status == http.StatusOK {
		var session sessionResponse
		decodeErr := json.Unmarshal(result.Body, &session)
		validSession := session.SessionID == id && session.ArchiveID != "" &&
			session.Status != "" && session.ExpiresAt != ""

		if decodeErr != nil || !validSession {
			responseProblem := httpx.NewProblem(
				r,
				http.StatusBadGateway,
				"invalid-upstream",
				"Invalid Upstream Response",
				"Capture returned invalid session metadata.",
			)
			httpx.WriteProblem(w, responseProblem)
			return
		}
	}

	common.ForwardJSON(w, r, result, http.StatusOK, "Capture")
}
