package application

import (
	"context"
	"encoding/json"
)

const (
	archiveDecisionPublish = "PUBLISH"
	archiveReplayReady     = "READY"
)

var publishedArchiveStatuses = map[string]bool{
	"COMPLETED":             true,
	"COMPLETED_WITH_ERRORS": true,
}

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

func (a Application) RequirePublishedArchive(ctx context.Context, id string) error {
	raw, err := a.GetArchive(ctx, id)

	if err != nil {
		return err
	}

	var status ArchiveStatus

	if err := json.Unmarshal(raw, &status); err != nil {
		return ErrInvalidUpstream
	}

	isPublished := status.Decision == archiveDecisionPublish &&
		status.Replay.Status == archiveReplayReady &&
		publishedArchiveStatuses[status.Status]

	if !isPublished {
		return ErrArchiveNotPublished
	}

	return nil
}
