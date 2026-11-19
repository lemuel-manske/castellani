package assembly

import (
 "context"
 "encoding/json"
 "errors"

 "github.com/lemuel-manske/unnamed/services/gateway/application"
 "github.com/lemuel-manske/unnamed/services/gateway/clients/coordinator"
 "github.com/lemuel-manske/unnamed/services/gateway/common/archive"
)

type coordinatorAdapter struct { client *coordinator.Client }

func (a coordinatorAdapter) CreateArchive(ctx context.Context, key string, raw []byte) (archive.Accepted, error) {
 result, err := a.client.CreateArchive(ctx, key, raw)
 if err != nil { return archive.Accepted{}, coordinatorError(err) }
 return archive.Accepted{ArchiveID: result.ArchiveID, Status: result.Status, StatusURL: result.StatusURL}, nil
}

func (a coordinatorAdapter) GetArchive(ctx context.Context, id string) (json.RawMessage, error) {
 result, err := a.client.GetArchive(ctx, id)
 if err != nil { return nil, coordinatorError(err) }
 return json.RawMessage(result), nil
}

func coordinatorError(err error) error {
 var failure *coordinator.Failure
 switch {
 case errors.Is(err, coordinator.ErrInvalidResponse):
  return application.ErrInvalidUpstream
 case errors.As(err, &failure):
  return &application.DependencyFailure{
   Status: failure.Problem.Status,
   Type: failure.Problem.Type,
   Title: failure.Problem.Title,
   Detail: failure.Problem.Detail,
  }
 default:
  return errUnavailable(err)
 }
}
