// Package application provides the Gateway's application use cases.
package application

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/common/archive"
)

var ErrInvalidArchiveID = errors.New("archive ID must be a nonempty path segment")

func (a Application) CreateArchive(
	ctx context.Context,
	key string,
	submission archive.Submission,
	raw []byte,
) (ArchiveAccepted, error) {
	if err := submission.Validate(); err != nil {
		return ArchiveAccepted{}, &ValidationError{
			Cause: err,
		}
	}

	return a.coordinator.CreateArchive(
		ctx,
		key,
		raw,
	)
}

func (a Application) GetArchive(ctx context.Context, id string) (json.RawMessage, error) {
	if !httpx.ValidPathSegment(id) {
		return nil, ErrInvalidArchiveID
	}

	return a.coordinator.GetArchive(ctx, id)
}
