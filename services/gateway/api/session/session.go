// Package sessionapi provides HTTP handlers for the Sessions API.
package sessionapi

import (
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/castellani/services/gateway/api/response"
	"github.com/lemuel-manske/castellani/services/gateway/application"
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

type Handler struct {
	app application.Application
}

type updateRequest struct {
	Status string `json:"status"`
}

func NewHandler(app application.Application) Handler {
	return Handler{app: app}
}

func (h Handler) Create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get(httpx.IdempotencyHeader)

	if !httpx.ValidIdempotencyKey(key) {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-idempotency-key", "Invalid Idempotency Key", "Idempotency-Key is required and must contain 8 to 200 characters."))
		return
	}

	var input application.SessionRequest
	raw, err := httpx.DecodeJSONBytes(w, r, &input)

	if err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-session", "Invalid Session", err.Error()))
		return
	}

	result, err := h.app.CreateSession(r.Context(), key, input, raw)

	if err != nil {
		response.WriteDependencyError(w, r, err, "Capture", "Capture returned invalid session metadata.")
		return
	}

	w.Header().Set(httpx.LocationHeader, common.SessionPathPrefix+url.PathEscape(result.SessionID))
	httpx.JSON(w, http.StatusCreated, result)
}

func (h Handler) Get(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, common.SessionIDParameter)

	if !httpx.ValidPathSegment(id) {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-session-id", "Invalid Session ID", "Invalid session ID."))
		return
	}

	result, err := h.app.GetSession(r.Context(), id)

	if err != nil {
		response.WriteDependencyError(w, r, err, "Capture", "Capture returned invalid session metadata.")
		return
	}

	httpx.JSON(w, http.StatusOK, result)
}

func (h Handler) Update(w http.ResponseWriter, r *http.Request) {
	var input updateRequest
	raw, err := httpx.DecodeJSONBytes(w, r, &input)

	if err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-session", "Invalid Session", err.Error()))
		return
	}

	id := chi.URLParam(r, common.SessionIDParameter)

	if !httpx.ValidPathSegment(id) {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-session-id", "Invalid Session ID", "Invalid session ID."))
		return
	}

	result, err := h.app.UpdateSession(r.Context(), id, raw)

	if err != nil {
		response.WriteDependencyError(w, r, err, "Capture", "Capture returned invalid session metadata.")
		return
	}

	httpx.JSON(w, http.StatusOK, result)
}
