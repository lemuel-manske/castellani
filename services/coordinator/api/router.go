package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"mime"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

const (
	maxRequestBytes         = 64 << 10
	minIdempotencyKeyLength = 8
	maxIdempotencyKeyLength = 200

	archivesPath  = "/archives"
	archivePath   = "/archives/{archiveId}"
	archiveIDPath = "archiveId"
	healthLive    = "/health/live"
	healthReady   = "/health/ready"

	idempotencyHeader = "Idempotency-Key"
	contentTypeHeader = "Content-Type"
	mediaTypeJSON     = "application/json"
	mediaTypeProblem  = "application/problem+json"
	healthMediaType   = "text/plain; charset=utf-8"
	healthResponse    = "ok\n"
	problemTypePrefix = "urn:distributed-web-archive:problem:"
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
					problem(w, r, http.StatusInternalServerError, "internal", "Internal Server Error", "Request handling failed.")
				}
			}()

			next.ServeHTTP(w, r)
		})
	}
}

func health(w http.ResponseWriter, status int) {
	w.Header().Set(contentTypeHeader, healthMediaType)
	w.WriteHeader(status)
	_, _ = io.WriteString(w, healthResponse)
}

func validIdempotencyKey(key string) bool {
	validLength := len(key) >= minIdempotencyKeyLength && len(key) <= maxIdempotencyKeyLength
	noOuterWhitespace := strings.TrimSpace(key) == key

	return validLength && noOuterWhitespace
}

func create(w http.ResponseWriter, r *http.Request, service Archives) {
	key := r.Header.Get(idempotencyHeader)

	if !validIdempotencyKey(key) {
		problem(w, r, http.StatusBadRequest, "idempotency-key", "Invalid Idempotency Key", "Idempotency-Key must be 8 to 200 characters without surrounding whitespace.")
		return
	}

	mediaType, _, err := mime.ParseMediaType(r.Header.Get(contentTypeHeader))

	if err != nil || mediaType != mediaTypeJSON {
		problem(w, r, http.StatusBadRequest, "content-type", "Invalid Content Type", "Expected application/json.")
		return
	}

	data, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxRequestBytes))

	if err != nil {
		problem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Invalid or oversized request.")
		return
	}

	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()

	var submission archive.Submission

	if err := decoder.Decode(&submission); err != nil {
		problem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected a valid archive JSON object.")
		return
	}

	var extra any

	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		problem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected exactly one JSON object.")
		return
	}

	accepted, err := service.Create(r, key, submission)

	if err != nil {
		writeError(w, r, err)
		return
	}

	w.Header().Set("Location", accepted.StatusURL)
	respond(w, http.StatusAccepted, accepted)
}

func status(w http.ResponseWriter, r *http.Request, service Archives, id string) {
	record, err := service.Get(r, id)

	if err != nil {
		writeError(w, r, err)
		return
	}

	respond(w, http.StatusOK, record)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, application.ErrInvalid):
		problem(w, r, http.StatusUnprocessableEntity, "invalid-archive", "Invalid Archive", err.Error())
	case errors.Is(err, application.ErrConflict):
		problem(w, r, http.StatusConflict, "idempotency-conflict", "Conflict", "Idempotency-Key was used for a different archive request.")
	case errors.Is(err, application.ErrNotFound):
		problem(w, r, http.StatusNotFound, "not-found", "Not Found", "Archive does not exist.")
	default:
		problem(w, r, http.StatusServiceUnavailable, "coordinator-unavailable", "Coordinator Unavailable", "The operation could not be confirmed. Retry with the same Idempotency-Key.")
	}
}

type problemDocument struct {
	Type     string `json:"type"`
	Title    string `json:"title"`
	Status   int    `json:"status"`
	Detail   string `json:"detail,omitempty"`
	Instance string `json:"instance,omitempty"`
}

func problem(w http.ResponseWriter, r *http.Request, status int, kind, title, detail string) {
	document := problemDocument{
		Type:     problemTypePrefix + kind,
		Title:    title,
		Status:   status,
		Detail:   detail,
		Instance: r.URL.Path,
	}

	w.Header().Set(contentTypeHeader, mediaTypeProblem)
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(document)
}

func respond(w http.ResponseWriter, status int, payload any) {
	w.Header().Set(contentTypeHeader, mediaTypeJSON)
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
