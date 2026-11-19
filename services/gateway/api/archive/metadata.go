package archiveapi

import (
	"encoding/json"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

const (
	PagesPath       = "/archives/{archiveId}/pages"
	SnapshotPath    = "/archives/{archiveId}/snapshots/{snapshotId}"
	pagesSuffix     = "/pages"
	snapshotSegment = "/snapshots/"
	snapshotParam   = "snapshotId"
)

type MetadataHandler struct {
	client *upstream.Client
}

func NewMetadataHandler(client *upstream.Client) MetadataHandler {
	return MetadataHandler{client: client}
}

func (h MetadataHandler) Pages(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, httpx.ArchiveIDParameter)

	if !httpx.ValidateID(id) {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-archive-id", "Invalid Archive ID", "Invalid archive ID."))
		return
	}

	if err := httpx.ValidatePagination(r.URL.Query()); err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-pagination", "Invalid Pagination", err.Error()))
		return
	}

	path := httpx.ArchivePathPrefix + url.PathEscape(id) + pagesSuffix
	result, err := h.client.JSON(r.Context(), http.MethodGet, path, r.URL.RawQuery, "", nil)

	if err != nil {
		httpx.UpstreamError(w, r, err, "Capture")
		return
	}

	if result.Status == http.StatusOK {
		var document struct { Items []json.RawMessage `json:"items"` }
		decodeErr := json.Unmarshal(result.Body, &document)

		if decodeErr != nil || document.Items == nil {
			httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Capture returned invalid page metadata."))
			return
		}
	}

	httpx.ForwardJSON(w, r, result, http.StatusOK, "Capture")
}

func (h MetadataHandler) Snapshot(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, httpx.ArchiveIDParameter)
	snapshotID := chi.URLParam(r, snapshotParam)
	validIDs := httpx.ValidateID(id) && httpx.ValidateID(snapshotID)

	if !validIDs {
		httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-snapshot-id", "Invalid Snapshot ID", "Invalid archive or snapshot ID."))
		return
	}

	path := httpx.ArchivePathPrefix + url.PathEscape(id) + snapshotSegment + url.PathEscape(snapshotID)
	result, err := h.client.JSON(r.Context(), http.MethodGet, path, "", "", nil)

	if err != nil {
		httpx.UpstreamError(w, r, err, "Capture")
		return
	}

	if result.Status == http.StatusOK {
		var document struct {
			ArchiveID  string `json:"archiveId"`
			SnapshotID string `json:"snapshotId"`
			URL        string `json:"url"`
			CapturedAt string `json:"capturedAt"`
		}
		decodeErr := json.Unmarshal(result.Body, &document)
		validSnapshot := document.ArchiveID == id && document.SnapshotID == snapshotID &&
			document.URL != "" && document.CapturedAt != ""

		if decodeErr != nil || !validSnapshot {
			httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Capture returned invalid snapshot metadata."))
			return
		}
	}

	httpx.ForwardJSON(w, r, result, http.StatusOK, "Capture")
}
