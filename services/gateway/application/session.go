package application

import "context"

func (a Application) CreateSession(
	ctx context.Context,
	key string,
	input SessionRequest,
	raw []byte,
) (Session, error) {
	if a.capture == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.capture.CreateSession(ctx, key, input, raw)
}

func (a Application) GetSession(ctx context.Context, sessionID string) (Session, error) {
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
	if a.capture == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.capture.UpdateSession(ctx, sessionID, raw)
}
