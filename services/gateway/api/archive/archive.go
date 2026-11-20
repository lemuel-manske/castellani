// Package archiveapi provides HTTP handlers for the Archiving API
package archiveapi

import (
	"errors"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/castellani/services/gateway/application"
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

type Handler struct {
	app application.Application
}

func NewHandler(app application.Application) Handler {
	return Handler{
		app: app,
	}
}

func (h Handler) Create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get(httpx.IdempotencyHeader)

	if !httpx.ValidIdempotencyKey(key) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"idempotency-key",
			"Invalid Idempotency Key",
			"Idempotency-Key must be 8 to 200 characters without surrounding whitespace.",
		))

		return
	}

	var submission application.Submission
	data, err := httpx.DecodeJSONBytes(
		w,
		r,
		&submission,
	)

	if err != nil {
		switch {
		case errors.Is(err, httpx.ErrContentType):
			httpx.WriteProblem(w, httpx.NewProblem(
				r,
				http.StatusBadRequest,
				"content-type",
				"Invalid Content Type",
				"Expected application/json.",
			))
		case errors.Is(err, httpx.ErrExtraJSON):
			httpx.WriteProblem(w, httpx.NewProblem(
				r,
				http.StatusBadRequest,
				"invalid-json",
				"Invalid Request",
				"Expected exactly one JSON object.",
			))
		case errors.Is(err, httpx.ErrInvalidJSON):
			httpx.WriteProblem(w, httpx.NewProblem(
				r,
				http.StatusBadRequest,
				"invalid-json",
				"Invalid Request",
				"Expected a valid archive JSON object.",
			))
		default:
			httpx.WriteProblem(w, httpx.NewProblem(
				r,
				http.StatusBadRequest,
				"invalid-json",
				"Invalid Request",
				"The archive request is invalid or exceeds the size limit.",
			))
		}

		return
	}

	accepted, err := h.app.CreateArchive(
		r.Context(),
		key,
		submission,
		data,
	)

	if err != nil {
		writeFailure(
			w,
			r,
			err,
			"Admission could not be confirmed. Retry with the same Idempotency-Key.",
		)

		return
	}

	accepted.StatusURL = common.ArchivePathPrefix + url.PathEscape(accepted.ArchiveID)

	w.Header().Set(httpx.LocationHeader, accepted.StatusURL)

	httpx.JSON(
		w,
		http.StatusAccepted,
		accepted,
	)
}

func (h Handler) Status(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, common.ArchiveIDParameter)

	document, err := h.app.GetArchive(r.Context(), id)

	if err != nil {
		writeFailure(
			w,
			r,
			err,
			"Archive status is temporarily unavailable.",
		)

		return
	}

	httpx.JSON(
		w,
		http.StatusOK,
		document,
	)
}

func writeFailure(
	w http.ResponseWriter,
	r *http.Request,
	err error,
	unavailableDetail string,
) {
	var dependencyFailure *application.DependencyFailure

	var validation *application.ValidationError

	switch {
	case errors.As(err, &validation):
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusUnprocessableEntity,
			"invalid-archive",
			"Invalid Archive",
			validation.Error(),
		))

	case errors.Is(err, application.ErrInvalidArchiveID):
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-archive-id",
			"Invalid Archive ID",
			err.Error(),
		))

	case errors.As(err, &dependencyFailure):
		httpx.WriteProblem(w, httpx.Problem{
			Type:     dependencyFailure.Type,
			Title:    dependencyFailure.Title,
			Status:   dependencyFailure.Status,
			Detail:   dependencyFailure.Detail,
			Instance: r.URL.Path,
		})

	case errors.Is(err, application.ErrInvalidUpstream):
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadGateway,
			"invalid-upstream",
			"Invalid Upstream Response",
			"Coordinator returned an unexpected response.",
		))

	default:
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusServiceUnavailable,
			"coordinator-unavailable",
			"Coordinator Unavailable",
			unavailableDetail,
		))
	}
}
