package sessionapi

import (
	"encoding/json"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	sharedhttp "github.com/lemuel-manske/castellani/libs/httpx"
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
	key := r.Header.Get(sharedhttp.IdempotencyHeader)

	if !sharedhttp.ValidateIdempotencyKey(key) {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-idempotency-key",
			"Invalid Idempotency Key",
			"Idempotency-Key is required and must contain 8 to 200 characters.",
		)
		sharedhttp.WriteProblem(w, responseProblem)
		return
	}

	var input createRequest
	raw, err := readJSON(w, r, &input)

	if err != nil {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			err.Error(),
		)
		sharedhttp.WriteProblem(w, responseProblem)
		return
	}

	if !sharedhttp.ValidPathSegment(input.ArchiveID) || !sharedhttp.ValidHTTPURL(input.TargetURL) {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			"Expected archiveId and absolute HTTP(S) targetUrl.",
		)
		sharedhttp.WriteProblem(w, responseProblem)
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
	validSession := sharedhttp.ValidPathSegment(created.SessionID) && created.ArchiveID == input.ArchiveID &&
		created.Status != "" && created.ExpiresAt != ""

	if decodeErr != nil || !validSession {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadGateway,
			"invalid-upstream",
			"Invalid Upstream Response",
			"Capture returned invalid session metadata.",
		)
		sharedhttp.WriteProblem(w, responseProblem)
		return
	}

	location := pathPrefix + url.PathEscape(created.SessionID)

	w.Header().Set(sharedhttp.LocationHeader, location)
	httpx.ForwardJSON(w, r, result, http.StatusCreated, "Capture")
}

func (h Handler) Get(w http.ResponseWriter, r *http.Request) {
	h.forwardSession(w, r, http.MethodGet, nil)
}

func (h Handler) Update(w http.ResponseWriter, r *http.Request) {
	var input updateRequest
	raw, err := readJSON(w, r, &input)

	if err != nil {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			err.Error(),
		)
		sharedhttp.WriteProblem(w, responseProblem)
		return
	}

	validStatus := input.Status == "COMPLETED" || input.Status == "CANCELLED"

	if !validStatus {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			"status must be COMPLETED or CANCELLED.",
		)
		sharedhttp.WriteProblem(w, responseProblem)
		return
	}

	h.forwardSession(w, r, http.MethodPut, raw)
}

func (h Handler) forwardSession(w http.ResponseWriter, r *http.Request, method string, body []byte) {
	id := chi.URLParam(r, idParameter)

	if !sharedhttp.ValidPathSegment(id) {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session-id",
			"Invalid Session ID",
			"Invalid session ID.",
		)
		sharedhttp.WriteProblem(w, responseProblem)
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
			responseProblem := sharedhttp.NewProblem(
				r,
				http.StatusBadGateway,
				"invalid-upstream",
				"Invalid Upstream Response",
				"Capture returned invalid session metadata.",
			)
			sharedhttp.WriteProblem(w, responseProblem)
			return
		}
	}

	httpx.ForwardJSON(w, r, result, http.StatusOK, "Capture")
}

func readJSON(w http.ResponseWriter, r *http.Request, destination any) ([]byte, error) {
	return sharedhttp.DecodeJSONBytes(w, r, destination)
}
