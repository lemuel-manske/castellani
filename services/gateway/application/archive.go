package application

import (
	"context"
	"encoding/json"
)

func (a Application) CreateArchive(
	ctx context.Context,
	key string,
	raw []byte,
) (ArchiveAccepted, error) {
	if a.coordinator == nil {
		return ArchiveAccepted{}, ErrDependencyUnavailable
	}

	return a.coordinator.CreateArchive(
		ctx,
		key,
		raw,
	)
}

func (a Application) GetArchive(ctx context.Context, id string) (json.RawMessage, error) {
	if a.coordinator == nil {
		return nil, ErrDependencyUnavailable
	}

	return a.coordinator.GetArchive(ctx, id)
}
