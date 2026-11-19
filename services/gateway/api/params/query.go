// Package params decodes public HTTP query parameters into application inputs.
package params

import (
 "errors"
 "net/url"
 "strconv"

 "github.com/lemuel-manske/unnamed/services/gateway/application"
)

func Pagination(values url.Values) (application.Pagination, error) {
 limits := values["limit"]

 if len(limits) > 1 {
  return application.Pagination{}, errors.New("limit must be supplied once")
 }

 if len(values["cursor"]) > 1 {
  return application.Pagination{}, errors.New("cursor must be supplied once")
 }

 pagination := application.Pagination{Cursor: values.Get("cursor")}

 if len(limits) == 1 {
  limit, err := strconv.Atoi(limits[0])
  if err != nil {
   return application.Pagination{}, errors.New("limit must be an integer")
  }
  pagination.Limit = &limit
 }

 if err := pagination.Validate(); err != nil {
  return application.Pagination{}, err
 }

 return pagination, nil
}

func Search(values url.Values) (application.SearchQuery, error) {
 allowed := map[string]bool{
  "q": true, "limit": true, "cursor": true, "collectionId": true,
  "archiveId": true, "snapshotId": true, "capturedFrom": true, "capturedTo": true,
 }

 for name, entries := range values {
  if !allowed[name] || len(entries) != 1 {
   return application.SearchQuery{}, errors.New("unknown or repeated search parameter")
  }
 }

 pagination, err := Pagination(values)
 if err != nil {
  return application.SearchQuery{}, err
 }

 query := application.SearchQuery{
  Text: values.Get("q"),
  CollectionID: values.Get("collectionId"),
  ArchiveID: values.Get("archiveId"),
  SnapshotID: values.Get("snapshotId"),
  CapturedFrom: values.Get("capturedFrom"),
  CapturedTo: values.Get("capturedTo"),
  Pagination: pagination,
 }

 if err := query.Validate(); err != nil {
  return application.SearchQuery{}, err
 }

 return query, nil
}
