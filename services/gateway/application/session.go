package application

import (
 "context"
 "encoding/json"
 "fmt"

 "github.com/lemuel-manske/castellani/libs/httpx"
)

const (
 SessionCompleted = "COMPLETED"
 SessionCancelled = "CANCELLED"
)

func (a Application) CreateSession(ctx context.Context, key string, input SessionRequest, raw []byte) (json.RawMessage, error) {
 if !httpx.ValidIdempotencyKey(key) {
  return nil, fmt.Errorf("%w: invalid idempotency key", ErrInvalidSession)
 }
 if err := input.Validate(); err != nil { return nil, err }
 if a.capture == nil { return nil, ErrDependencyUnavailable }
 return a.capture.CreateSession(ctx, key, input, raw)
}

func (a Application) GetSession(ctx context.Context, sessionID string) (json.RawMessage, error) {
 if err := validateSessionID(sessionID); err != nil { return nil, err }
 if a.capture == nil { return nil, ErrDependencyUnavailable }
 return a.capture.GetSession(ctx, sessionID)
}

func (a Application) UpdateSession(ctx context.Context, sessionID, status string, raw []byte) (json.RawMessage, error) {
 if err := validateSessionID(sessionID); err != nil { return nil, err }
 if status != SessionCompleted && status != SessionCancelled {
  return nil, fmt.Errorf("%w: status must be COMPLETED or CANCELLED", ErrInvalidSession)
 }
 if a.capture == nil { return nil, ErrDependencyUnavailable }
 return a.capture.UpdateSession(ctx, sessionID, status, raw)
}
