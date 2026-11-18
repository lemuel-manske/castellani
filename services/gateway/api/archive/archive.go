package archiveapi

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"net/url"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/archive"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/coordinator"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
)

const maxRequestBytes = 64 << 10

type Handler struct {
	app application.Application
}

func NewHandler(app application.Application) Handler {
	return Handler{app: app}
}

func (h Handler) Create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get("Idempotency-Key")
	if len(key) < 8 || len(key) > 200 || strings.TrimSpace(key) != key {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "idempotency-key", "Invalid Idempotency Key", "Idempotency-Key must be 8 to 200 characters without surrounding whitespace.")
		return
	}
	mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "content-type", "Invalid Content Type", "Expected application/json.")
		return
	}

	data, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxRequestBytes))
	if err != nil {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "The archive request is invalid or exceeds the size limit.")
		return
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var submission archive.Submission
	if err := decoder.Decode(&submission); err != nil {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected a valid archive JSON object.")
		return
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-json", "Invalid Request", "Expected exactly one JSON object.")
		return
	}
	if err := submission.Validate(); err != nil {
		httpx.WriteProblem(w, r, http.StatusUnprocessableEntity, "invalid-archive", "Invalid Archive", err.Error())
		return
	}

	accepted, err := h.app.CreateArchive(r.Context(), key, data)
	if err != nil {
		writeCoordinatorError(w, r, err, "Admission could not be confirmed. Retry with the same Idempotency-Key.")
		return
	}
	accepted.StatusURL = "/archives/" + url.PathEscape(accepted.ArchiveID)
	w.Header().Set("Location", accepted.StatusURL)
	httpx.JSON(w, http.StatusAccepted, accepted)
}

func (h Handler) Status(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "archiveId")
	if !archive.ValidID(id) {
		httpx.WriteProblem(w, r, http.StatusBadRequest, "invalid-archive-id", "Invalid Archive ID", "Archive ID must be a nonempty path segment.")
		return
	}
	document, err := h.app.GetArchive(r.Context(), id)
	if err != nil {
		writeCoordinatorError(w, r, err, "Archive status is temporarily unavailable.")
		return
	}
	httpx.JSON(w, http.StatusOK, document)
}

func writeCoordinatorError(w http.ResponseWriter, r *http.Request, err error, unavailableDetail string) {
	var failure *coordinator.Failure
	switch {
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
