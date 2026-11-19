package archiveapi

import (
	"errors"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/archive"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/coordinator"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
)

type Handler struct {
	app application.Application
}

func NewHandler(app application.Application) Handler {
	return Handler{app: app}
}

func (h Handler) Create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get(httpx.IdempotencyHeader)

	if !httpx.ValidateIdempotencyKey(key) {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "idempotency-key", "Invalid Idempotency Key", "Idempotency-Key must be 8 to 200 characters without surrounding whitespace.")
		return
	}

	var submission archive.Submission
	data, err := httpx.DecodeJSONBytes(w, r, &submission)

	if err != nil {
		switch {
		case errors.Is(err, httpx.ErrContentType):
			httpx.WriteProblem(w, r, http.StatusBadRequest, "content-type", "Invalid Content Type", "Expected application/json.")
		case errors.Is(err, httpx.ErrExtraJSON):
			httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected exactly one JSON object.")
		case errors.Is(err, httpx.ErrInvalidJSON):
			httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected a valid archive JSON object.")
		default:
			httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "The archive request is invalid or exceeds the size limit.")
		}

		return
	}

	accepted, err := h.app.CreateArchive(r.Context(), key, submission, data)

	if err != nil {
		writeCoordinatorError(w, r, err, "Admission could not be confirmed. Retry with the same Idempotency-Key.")
		return
	}

	accepted.StatusURL = httpx.ArchivePathPrefix + url.PathEscape(accepted.ArchiveID)

	w.Header().Set(httpx.LocationHeader, accepted.StatusURL)

	httpx.JSON(w, http.StatusAccepted, accepted)
}

func (h Handler) Status(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, httpx.ArchiveIDParameter)

	document, err := h.app.GetArchive(r.Context(), id)

	if err != nil {
		writeCoordinatorError(w, r, err, "Archive status is temporarily unavailable.")
		return
	}

	httpx.JSON(w, http.StatusOK, document)
}

func writeCoordinatorError(w http.ResponseWriter, r *http.Request, err error, unavailableDetail string) {
	var failure *coordinator.Failure

	var validation *application.ValidationError

	switch {
	case errors.As(err, &validation):
		httpx.WriteProblem(w, r, http.StatusUnprocessableEntity, "invalid-archive", "Invalid Archive", validation.Error())

	case errors.Is(err, application.ErrInvalidArchiveID):
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-archive-id", "Invalid Archive ID", err.Error())

	case errors.As(err, &failure):
		p := failure.Problem
		p.Instance = r.URL.Path
		httpx.Write(w, p)

	case errors.Is(err, coordinator.ErrInvalidResponse):
		httpx.WriteProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Coordinator returned an unexpected response.")

	default:
		httpx.WriteProblem(w, r, http.StatusServiceUnavailable, "coordinator-unavailable", "Coordinator Unavailable", unavailableDetail)
	}
}
