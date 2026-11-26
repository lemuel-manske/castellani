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

type SessionsHandler struct {
	app application.Application
}

type updateRequest struct {
	Status string `json:"status"`
}

func NewSessionsHandler(app application.Application) SessionsHandler {
	return SessionsHandler{
		app: app,
	}
}

func (h SessionsHandler) Create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get(httpx.HeaderIdempotencyKey)

	if !httpx.ValidIdempotencyKey(key) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-idempotency-key",
			"Invalid Idempotency Key",
			"Idempotency-Key is required and must contain 8 to 200 characters.",
		))

		return
	}

	var input application.SessionRequest
	raw, err := httpx.DecodeJSONBytes(
		w,
		r,
		&input,
	)

	if err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			err.Error(),
		))

		return
	}

	result, err := h.app.CreateSession(
		r.Context(),
		key,
		input,
		raw,
	)

	if err != nil {
		response.WriteDependencyError(
			w,
			r,
			err,
			"Capture login manager",
			"Capture login manager returned invalid session metadata.",
		)

		return
	}

	w.Header().Set(httpx.HeaderLocation, common.SessionPathPrefix+url.PathEscape(result.SessionID))
	httpx.JSON(
		w,
		http.StatusCreated,
		withBrowserURL(result),
	)
}

func (h SessionsHandler) Get(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, common.SessionIDParameter)

	if !httpx.ValidPathSegment(id) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session-id",
			"Invalid Session ID",
			"Invalid session ID.",
		))

		return
	}

	result, err := h.app.GetSession(r.Context(), id)

	if err != nil {
		response.WriteDependencyError(
			w,
			r,
			err,
			"Capture login manager",
			"Capture login manager returned invalid session metadata.",
		)

		return
	}

	httpx.JSON(
		w,
		http.StatusOK,
		withBrowserURL(result),
	)
}

func (h SessionsHandler) Update(w http.ResponseWriter, r *http.Request) {
	var input updateRequest
	raw, err := httpx.DecodeJSONBytes(
		w,
		r,
		&input,
	)

	if err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session",
			"Invalid Session",
			err.Error(),
		))

		return
	}

	id := chi.URLParam(r, common.SessionIDParameter)

	if !httpx.ValidPathSegment(id) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session-id",
			"Invalid Session ID",
			"Invalid session ID.",
		))

		return
	}

	result, err := h.app.UpdateSession(
		r.Context(),
		id,
		raw,
	)

	if err != nil {
		response.WriteDependencyError(
			w,
			r,
			err,
			"Capture login manager",
			"Capture login manager returned invalid session metadata.",
		)

		return
	}

	httpx.JSON(
		w,
		http.StatusOK,
		withBrowserURL(result),
	)
}

func withBrowserURL(session application.Session) application.Session {
	session.BrowserURL = common.SessionPathPrefix +
		url.PathEscape(session.SessionID) +
		"/browser"

	return session
}
