package application

import (
	"context"
	"fmt"

	"github.com/lemuel-manske/castellani/libs/httpx"
)

const (
	SessionCompleted = "COMPLETED"
	SessionCancelled = "CANCELLED"
)

func (a Application) CreateSession(
	ctx context.Context,
	key string,
	input SessionRequest,
	raw []byte,
) (Session, error) {
	if !httpx.ValidIdempotencyKey(key) {
		return Session{}, fmt.Errorf("%w: invalid idempotency key", ErrInvalidSession)
	}

	if err := input.Validate(); err != nil {
		return Session{}, err
	}

	if a.capture == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.capture.CreateSession(
		ctx,
		key,
		input,
		raw,
	)
}

func (a Application) GetSession(ctx context.Context, sessionID string) (Session, error) {
	if err := validateSessionID(sessionID); err != nil {
		return Session{}, err
	}

	if a.capture == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.capture.GetSession(ctx, sessionID)
}

func (a Application) UpdateSession(
	ctx context.Context,
	sessionID, status string,
	raw []byte,
) (Session, error) {
	if err := validateSessionID(sessionID); err != nil {
		return Session{}, err
	}

	if status != SessionCompleted && status != SessionCancelled {
		return Session{}, fmt.Errorf("%w: status must be COMPLETED or CANCELLED", ErrInvalidSession)
	}

	if a.capture == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.capture.UpdateSession(
		ctx,
		sessionID,
		raw,
	)
}
