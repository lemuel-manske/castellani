package assembly

import (
 "context"
 "errors"

 "github.com/lemuel-manske/unnamed/services/gateway/application"
 "github.com/lemuel-manske/unnamed/services/gateway/clients/search"
)

type searchAdapter struct { client *search.Client }

func (a searchAdapter) Search(ctx context.Context, query application.SearchQuery) (application.SearchResults, error) {
 result, err := a.client.Search(ctx, search.Query{
  Text: query.Text, CollectionID: query.CollectionID,
  ArchiveID: query.ArchiveID, SnapshotID: query.SnapshotID,
  CapturedFrom: query.CapturedFrom, CapturedTo: query.CapturedTo,
  Pagination: search.Pagination{Limit: query.Pagination.Limit, Cursor: query.Pagination.Cursor},
 })
 if err != nil { return application.SearchResults{}, searchError(err) }
 return application.SearchResults{Results: result.Results, NextCursor: result.NextCursor}, nil
}

func searchError(err error) error {
 var failure *search.Failure
 switch {
 case errors.Is(err, search.ErrInvalidResponse):
  return application.ErrInvalidUpstream
 case errors.Is(err, search.ErrUnavailable):
  return errUnavailable(err)
 case errors.As(err, &failure):
  return &application.DependencyFailure{
   Status: failure.Status, Type: failure.Type,
   Title: failure.Title, Detail: failure.Detail,
  }
 default:
  return errUnavailable(err)
 }
}
