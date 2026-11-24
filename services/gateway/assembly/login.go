package assembly

import (
	"context"

	"github.com/lemuel-manske/castellani/services/gateway/application"
	"github.com/lemuel-manske/castellani/services/gateway/clients/capture"
)

type loginAdapter struct {
	client *capture.Client
}

func (a loginAdapter) CreateSession(
	ctx context.Context,
	key string,
	input application.SessionRequest,
	raw []byte,
) (application.Session, error) {
	result, err := a.client.CreateSession(
		ctx,
		key,
		capture.SessionRequest{
			ArchiveID: input.ArchiveID,
			TargetURL: input.TargetURL,
		},
		raw,
	)

	if err != nil {
		return application.Session{}, captureError(err)
	}

	return mapSession(result), nil
}

func (a loginAdapter) GetSession(ctx context.Context, sessionID string) (application.Session, error) {
	result, err := a.client.GetSession(ctx, sessionID)

	if err != nil {
		return application.Session{}, captureError(err)
	}

	return mapSession(result), nil
}

func (a loginAdapter) UpdateSession(
	ctx context.Context,
	sessionID string,
	raw []byte,
) (application.Session, error) {
	result, err := a.client.UpdateSession(
		ctx,
		sessionID,
		raw,
	)

	if err != nil {
		return application.Session{}, captureError(err)
	}

	return mapSession(result), nil
}

func mapSession(result capture.Session) application.Session {
	return application.Session{
		SessionID:      result.SessionID,
		ArchiveID:      result.ArchiveID,
		Status:         result.Status,
		ExpiresAt:      result.ExpiresAt,
		AuthGeneration: result.AuthGeneration,
	}
}
