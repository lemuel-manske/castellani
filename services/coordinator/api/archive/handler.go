// Package archiveapi exposes the Coordinator archive HTTP endpoints.
package archiveapi

import (
	"errors"
	"net/http"
	"net/url"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/common"
	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
)

type Handler struct {
	app *application.Application
}

type SubmissionRequest struct {
	SeedURL        string   `json:"seedUrl"`
	CollectionID   string   `json:"collectionId,omitempty"`
	MaxDepth       *int     `json:"maxDepth"`
	MaxPages       *int     `json:"maxPages"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}

type AcceptedResponse struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	StatusURL string `json:"statusUrl"`
}

type ArchiveResponse struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`

	Capture struct {
		Captured int `json:"captured"`
		Failed   int `json:"failed"`
		Pending  int `json:"pending"`
	} `json:"capture"`

	Replay struct {
		Status string `json:"status"`
	} `json:"replay"`

	Search struct {
		Status   string `json:"status"`
		Indexed  int    `json:"indexed"`
		Expected int    `json:"expected"`
	} `json:"search"`
}

func NewHandler(app *application.Application) Handler {
	return Handler{
		app: app,
	}
}

func (h Handler) Create(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get(httpx.IdempotencyHeader)

	if !httpx.ValidIdempotencyKey(key) {
		problem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-idempotency-key",
			"Invalid Idempotency Key",
			"Idempotency-Key must be 8 to 200 characters without surrounding whitespace.",
		)

		httpx.WriteProblem(w, problem)

		return
	}

	var input SubmissionRequest

	if _, err := httpx.DecodeJSONBytes(
		w,
		r,
		&input,
	); err != nil {
		kind := "invalid-json"
		title := "Invalid Request"
		detail := "Expected one valid archive JSON object."

		if errors.Is(err, httpx.ErrContentType) {
			kind = "content-type"
			title = "Invalid Content Type"
			detail = "Expected application/json."
		}

		problem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			kind,
			title,
			detail,
		)

		httpx.WriteProblem(w, problem)

		return
	}

	submission := domain.Submission{
		SeedURL:        input.SeedURL,
		CollectionID:   input.CollectionID,
		MaxDepth:       input.MaxDepth,
		MaxPages:       input.MaxPages,
		AllowedOrigins: input.AllowedOrigins,
		AuthGeneration: input.AuthGeneration,
	}

	accepted, err := h.app.SubmitArchive(
		r.Context(),
		key,
		submission,
	)

	if err != nil {
		writeFailure(
			w,
			r,
			err,
		)

		return
	}

	statusURL := common.ArchivePathPrefix + url.PathEscape(accepted.ArchiveID)
	w.Header().Set(httpx.LocationHeader, statusURL)

	response := AcceptedResponse{
		ArchiveID: accepted.ArchiveID,
		Status:    domain.StatusAccepted,
		StatusURL: statusURL,
	}

	httpx.JSON(
		w,
		http.StatusAccepted,
		response,
	)
}

func (h Handler) Status(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue(common.ArchiveIDParameter)

	archive, err := h.app.GetArchive(r.Context(), id)

	if err != nil {
		writeFailure(
			w,
			r,
			err,
		)

		return
	}

	response := ArchiveResponse{
		ArchiveID: archive.ID,
		Status:    archive.Status,
	}

	response.Capture.Captured = archive.Capture.Captured
	response.Capture.Failed = archive.Capture.Failed
	response.Capture.Pending = archive.Capture.Pending
	response.Replay.Status = archive.Replay.Status
	response.Search.Status = archive.Search.Status
	response.Search.Indexed = archive.Search.Indexed
	response.Search.Expected = archive.Search.Expected

	httpx.JSON(
		w,
		http.StatusOK,
		response,
	)
}

func writeFailure(
	w http.ResponseWriter,
	r *http.Request,
	err error,
) {
	status := http.StatusServiceUnavailable
	kind := "storage-unavailable"
	title := "Archive Unavailable"
	detail := "The archive operation could not be completed."

	switch {
	case errors.Is(err, application.ErrInvalidSubmission):
		status = http.StatusUnprocessableEntity
		kind = "invalid-archive"
		title = "Invalid Archive"
		detail = err.Error()
	case errors.Is(err, application.ErrInvalidIdempotencyKey):
		status = http.StatusBadRequest
		kind = "invalid-idempotency-key"
		title = "Invalid Idempotency Key"
		detail = "Idempotency-Key is invalid."
	case errors.Is(err, application.ErrIdempotencyConflict):
		status = http.StatusConflict
		kind = "idempotency-conflict"
		title = "Idempotency Conflict"
		detail = "Idempotency-Key was used for a different archive submission."
	case errors.Is(err, application.ErrInvalidArchiveID):
		status = http.StatusBadRequest
		kind = "invalid-archive-id"
		title = "Invalid Archive ID"
		detail = "Archive ID is invalid."
	case errors.Is(err, application.ErrArchiveNotFound):
		status = http.StatusNotFound
		kind = "archive-not-found"
		title = "Archive Not Found"
		detail = "No archive exists with this ID."
	}

	problem := httpx.NewProblem(
		r,
		status,
		kind,
		title,
		detail,
	)

	httpx.WriteProblem(w, problem)
}
