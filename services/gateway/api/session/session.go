package sessionapi

import (
	"encoding/json"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

const (
	Path         = "/sessions"
	ResourcePath = "/sessions/{sessionId}"
	pathPrefix   = "/sessions/"
	idParameter  = "sessionId"
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

	if !httpx.ValidateIdempotencyKey(key) {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-idempotency-key", "Invalid Idempotency Key", "Idempotency-Key is required and must contain 8 to 200 characters.")
		return
	}

	var input createRequest
	raw, err := readJSON(w, r, &input)

	if err != nil {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-session", "Invalid Session", err.Error())
		return
	}

	if !httpx.ValidateID(input.ArchiveID) || !httpx.ValidateTargetURL(input.TargetURL) {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-session", "Invalid Session", "Expected archiveId and absolute HTTP(S) targetUrl.")
		return
	}

	result, err := h.client.JSON(r.Context(), http.MethodPost, Path, "", key, raw)

	if err != nil {
		httpx.UpstreamError(w, r, err, "Capture")
		return
	}

	if result.Status != http.StatusCreated {
		httpx.ForwardJSON(w, r, result, http.StatusCreated, "Capture")
		return
	}

	var created sessionResponse
	decodeErr := json.Unmarshal(result.Body, &created)
	validSession := httpx.ValidateID(created.SessionID) && created.ArchiveID == input.ArchiveID &&
		created.Status != "" && created.ExpiresAt != ""

	if decodeErr != nil || !validSession {
		httpx.WriteProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Capture returned invalid session metadata.")
		return
	}

	location := pathPrefix + url.PathEscape(created.SessionID)

	w.Header().Set(httpx.LocationHeader, location)
	httpx.ForwardJSON(w, r, result, http.StatusCreated, "Capture")
}

func (h Handler) Get(w http.ResponseWriter, r *http.Request) {
	h.forwardSession(w, r, http.MethodGet, nil)
}

func (h Handler) Update(w http.ResponseWriter, r *http.Request) {
	var input updateRequest
	raw, err := readJSON(w, r, &input)

	if err != nil {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-session", "Invalid Session", err.Error())
		return
	}

	validStatus := input.Status == "COMPLETED" || input.Status == "CANCELLED"

	if !validStatus {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-session", "Invalid Session", "status must be COMPLETED or CANCELLED.")
		return
	}

	h.forwardSession(w, r, http.MethodPut, raw)
}

func (h Handler) forwardSession(w http.ResponseWriter, r *http.Request, method string, body []byte) {
	id := chi.URLParam(r, idParameter)

	if !httpx.ValidateID(id) {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-session-id", "Invalid Session ID", "Invalid session ID.")
		return
	}

	path := pathPrefix + url.PathEscape(id)
	result, err := h.client.JSON(r.Context(), method, path, "", "", body)

	if err != nil {
		httpx.UpstreamError(w, r, err, "Capture")
		return
	}

	if result.Status == http.StatusOK {
		var session sessionResponse
		decodeErr := json.Unmarshal(result.Body, &session)
		validSession := session.SessionID == id && session.ArchiveID != "" &&
			session.Status != "" && session.ExpiresAt != ""

		if decodeErr != nil || !validSession {
			httpx.WriteProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Capture returned invalid session metadata.")
			return
		}
	}

	httpx.ForwardJSON(w, r, result, http.StatusOK, "Capture")
}

func readJSON(w http.ResponseWriter, r *http.Request, destination any) ([]byte, error) {
	return httpx.DecodeJSONBytes(w, r, destination)
}
