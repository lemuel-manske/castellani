package api

import (
	"errors"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

const (
	archivesPath  = "/archives"
	archivePath   = "/archives/{archiveId}"
	archiveIDPath = "archiveId"
	healthLive    = "/health/live"
	healthReady   = "/health/ready"

	idempotencyHeader = "Idempotency-Key"
	healthMediaType   = "text/plain; charset=utf-8"
	healthResponse    = "ok\\n"
)

type Archives interface {
	Create(*http.Request, string, archive.Submission) (archive.AcceptedResponse, error)
	Get(*http.Request, string) (archive.Status, error)
}

type serviceAdapter struct {
	app application.Service
}

func (s serviceAdapter) Create(r *http.Request, key string, submission archive.Submission) (archive.AcceptedResponse, error) {
	return s.app.Create(r.Context(), key, submission)
}

func (s serviceAdapter) Get(r *http.Request, id string) (archive.Status, error) {
	return s.app.Get(r.Context(), id)
}

func NewRouter(app application.Service, ready func() bool, logger *slog.Logger) http.Handler {
	return Router(serviceAdapter{app: app}, ready, logger)
}

func Router(service Archives, ready func() bool, logger *slog.Logger) http.Handler {
	router := chi.NewRouter()
	router.Use(recoverPanics(logger))

	router.Get(healthLive, func(w http.ResponseWriter, _ *http.Request) {
		health(w, http.StatusOK)
	})

	router.Get(healthReady, func(w http.ResponseWriter, _ *http.Request) {
		if !ready() {
			http.Error(w, "unavailable", http.StatusServiceUnavailable)
			return
		}

		health(w, http.StatusOK)
	})

	router.Post(archivesPath, func(w http.ResponseWriter, r *http.Request) {
		create(w, r, service)
	})
	router.Get(archivePath, func(w http.ResponseWriter, r *http.Request) {
		status(w, r, service, chi.URLParam(r, archiveIDPath))
	})

	return router
}

func recoverPanics(logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if recovered := recover(); recovered != nil {
					logger.Error("coordinator handler panic", "path", r.URL.Path)
					httpx.WriteProblem(w, r, http.StatusInternalServerError, "internal", "Internal Server Error", "Request handling failed.")
				}
			}()

			next.ServeHTTP(w, r)
		})
	}
}

func health(w http.ResponseWriter, status int) {
	w.Header().Set(httpx.HeaderContentType, healthMediaType)
	w.WriteHeader(status)
	_, _ = w.Write([]byte(healthResponse))
}

func create(w http.ResponseWriter, r *http.Request, service Archives) {
	key := r.Header.Get(idempotencyHeader)

	if !httpx.ValidateIdempotencyKey(key) {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "idempotency-key", "Invalid Idempotency Key", "Idempotency-Key must be 8 to 200 characters without surrounding whitespace.")
		return
	}

	var submission archive.Submission
	_, err := httpx.DecodeJSONBytes(w, r, &submission)

	if err != nil {
		switch {
		case errors.Is(err, httpx.ErrContentType):
			httpx.WriteProblem(w, r, http.StatusBadRequest, "content-type", "Invalid Content Type", "Expected application/json.")
		case errors.Is(err, httpx.ErrExtraJSON):
			httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected exactly one JSON object.")
		case errors.Is(err, httpx.ErrInvalidJSON):
			httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected a valid archive JSON object.")
		default:
			httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Invalid or oversized request.")
		}

		return
	}

	accepted, err := service.Create(r, key, submission)

	if err != nil {
		writeError(w, r, err)
		return
	}

	w.Header().Set("Location", accepted.StatusURL)
	httpx.JSON(w, http.StatusAccepted, accepted)
}

func status(w http.ResponseWriter, r *http.Request, service Archives, id string) {
	record, err := service.Get(r, id)

	if err != nil {
		writeError(w, r, err)
		return
	}

	httpx.JSON(w, http.StatusOK, record)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, application.ErrInvalid):
		httpx.WriteProblem(w, r, http.StatusUnprocessableEntity, "invalid-archive", "Invalid Archive", err.Error())
	case errors.Is(err, application.ErrConflict):
		httpx.WriteProblem(w, r, http.StatusConflict, "idempotency-conflict", "Conflict", "Idempotency-Key was used for a different archive request.")
	case errors.Is(err, application.ErrNotFound):
		httpx.WriteProblem(w, r, http.StatusNotFound, "not-found", "Not Found", "Archive does not exist.")
	default:
		httpx.WriteProblem(w, r, http.StatusServiceUnavailable, "coordinator-unavailable", "Coordinator Unavailable", "The operation could not be confirmed. Retry with the same Idempotency-Key.")
	}
}

