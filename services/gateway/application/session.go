package application

import "context"

func (a Application) CreateSession(
	ctx context.Context,
	key string,
	input SessionRequest,
	raw []byte,
) (Session, error) {
	if a.login == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.login.CreateSession(
		ctx,
		key,
		input,
		raw,
	)
}

func (a Application) GetSession(ctx context.Context, sessionID string) (Session, error) {
	if a.login == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.login.GetSession(ctx, sessionID)
}

func (a Application) UpdateSession(
	ctx context.Context,
	sessionID string,
	raw []byte,
) (Session, error) {
	if a.login == nil {
		return Session{}, ErrDependencyUnavailable
	}

	return a.login.UpdateSession(
		ctx,
		sessionID,
		raw,
	)
}
