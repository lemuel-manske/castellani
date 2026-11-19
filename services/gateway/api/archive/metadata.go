package archiveapi

import (
 "net/http"
 "strconv"

 "github.com/go-chi/chi/v5"
 "github.com/lemuel-manske/castellani/libs/httpx"
 "github.com/lemuel-manske/unnamed/services/gateway/application"
 "github.com/lemuel-manske/unnamed/services/gateway/api/response"
 "github.com/lemuel-manske/unnamed/services/gateway/common"
)

type MetadataHandler struct {
 app application.Application
}

func NewMetadataHandler(app application.Application) MetadataHandler {
 return MetadataHandler{app: app}
}

func (h MetadataHandler) Pages(w http.ResponseWriter, r *http.Request) {
 id := chi.URLParam(r, common.ArchiveIDParameter)

 if !httpx.ValidPathSegment(id) {
  httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-archive-id", "Invalid Archive ID", "Invalid archive ID."))
  return
 }

 if err := common.ValidatePagination(r.URL.Query()); err != nil {
  httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-pagination", "Invalid Pagination", err.Error()))
  return
 }

 pagination := application.Pagination{Cursor: r.URL.Query().Get("cursor")}
 if raw := r.URL.Query().Get("limit"); raw != "" {
  limit, err := strconv.Atoi(raw)
  if err != nil {
   httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-pagination", "Invalid Pagination", "limit must be an integer"))
   return
  }
  pagination.Limit = &limit
 }

 result, err := h.app.ListPages(r.Context(), id, pagination)
 if err != nil {
  response.WriteDependencyError(w, r, err, "Capture", "Capture returned invalid page metadata.")
  return
 }

 httpx.JSON(w, http.StatusOK, result)
}

func (h MetadataHandler) Snapshot(w http.ResponseWriter, r *http.Request) {
 archiveID := chi.URLParam(r, common.ArchiveIDParameter)
 snapshotID := chi.URLParam(r, common.SnapshotIDParameter)

 if !httpx.ValidPathSegment(archiveID) || !httpx.ValidPathSegment(snapshotID) {
  httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-snapshot-id", "Invalid Snapshot ID", "Invalid archive or snapshot ID."))
  return
 }

 result, err := h.app.GetSnapshot(r.Context(), archiveID, snapshotID)
 if err != nil {
  response.WriteDependencyError(w, r, err, "Capture", "Capture returned invalid snapshot metadata.")
  return
 }

 httpx.JSON(w, http.StatusOK, result)
}
