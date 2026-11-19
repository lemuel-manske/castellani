// Package searchapi provides HTTP handlers for the Searching API.
package searchapi

import (
 "net/http"
 "strconv"

 "github.com/lemuel-manske/castellani/libs/httpx"
 "github.com/lemuel-manske/unnamed/services/gateway/application"
 "github.com/lemuel-manske/unnamed/services/gateway/api/response"
 "github.com/lemuel-manske/unnamed/services/gateway/common"
)

type Handler struct { app application.Application }

func NewHandler(app application.Application) Handler { return Handler{app: app} }

func (h Handler) Search(w http.ResponseWriter, r *http.Request) {
 values := r.URL.Query()

 if err := common.ValidateSearch(values); err != nil {
  httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-search", "Invalid Search", err.Error()))
  return
 }

 query := application.SearchQuery{
  Text: values.Get("q"),
  CollectionID: values.Get("collectionId"),
  ArchiveID: values.Get("archiveId"),
  SnapshotID: values.Get("snapshotId"),
  CapturedFrom: values.Get("capturedFrom"),
  CapturedTo: values.Get("capturedTo"),
  Pagination: application.Pagination{Cursor: values.Get("cursor")},
 }

 if raw := values.Get("limit"); raw != "" {
  limit, err := strconv.Atoi(raw)
  if err != nil {
   httpx.WriteProblem(w, httpx.NewProblem(r, http.StatusBadRequest, "invalid-search", "Invalid Search", "limit must be an integer"))
   return
  }
  query.Pagination.Limit = &limit
 }

 result, err := h.app.Search(r.Context(), query)
 if err != nil {
  response.WriteDependencyError(w, r, err, "Search", "Search returned invalid results.")
  return
 }

 httpx.JSON(w, http.StatusOK, result)
}
