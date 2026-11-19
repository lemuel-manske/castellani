package archiveapi

import (
	"encoding/json"
	"net/http"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/common"
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
	id := chi.URLParam(r, common.ArchiveIDParameter)

	if !httpx.ValidPathSegment(id) {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-archive-id",
			"Invalid Archive ID",
			"Invalid archive ID.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	if err := common.ValidatePagination(r.URL.Query()); err != nil {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-pagination",
			"Invalid Pagination",
			err.Error(),
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	path := common.ArchivePathPrefix + url.PathEscape(id) + pagesSuffix
	result, err := h.client.JSON(r.Context(), http.MethodGet, path, r.URL.RawQuery, "", nil)

	if err != nil {
		common.UpstreamError(w, r, err, "Capture")
		return
	}

	if result.Status == http.StatusOK {
		var document struct { Items []json.RawMessage `json:"items"` }
		decodeErr := json.Unmarshal(result.Body, &document)

		if decodeErr != nil || document.Items == nil {
			responseProblem := httpx.NewProblem(
				r,
				http.StatusBadGateway,
				"invalid-upstream",
				"Invalid Upstream Response",
				"Capture returned invalid page metadata.",
			)
			httpx.WriteProblem(w, responseProblem)
			return
		}
	}

	common.ForwardJSON(w, r, result, http.StatusOK, "Capture")
}

func (h MetadataHandler) Snapshot(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, common.ArchiveIDParameter)
	snapshotID := chi.URLParam(r, snapshotParam)
	validIDs := httpx.ValidPathSegment(id) && httpx.ValidPathSegment(snapshotID)

	if !validIDs {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-snapshot-id",
			"Invalid Snapshot ID",
			"Invalid archive or snapshot ID.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	path := common.ArchivePathPrefix + url.PathEscape(id) + snapshotSegment + url.PathEscape(snapshotID)
	result, err := h.client.JSON(r.Context(), http.MethodGet, path, "", "", nil)

	if err != nil {
		common.UpstreamError(w, r, err, "Capture")
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
			responseProblem := httpx.NewProblem(
				r,
				http.StatusBadGateway,
				"invalid-upstream",
				"Invalid Upstream Response",
				"Capture returned invalid snapshot metadata.",
			)
			httpx.WriteProblem(w, responseProblem)
			return
		}
	}

	common.ForwardJSON(w, r, result, http.StatusOK, "Capture")
}
