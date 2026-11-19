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

type ArchiveAccepted struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	StatusURL string `json:"statusUrl"`
}

type ArchiveCoordinator interface {
	CreateArchive(
		context.Context,
		string,
		[]byte,
	) (ArchiveAccepted, error)

	GetArchive(context.Context, string) (json.RawMessage, error)
}

type Application struct {
	coordinator ArchiveCoordinator
	capture     Capture
	search      SearchService
}

type ValidationError struct {
	Cause error
}

func (e *ValidationError) Error() string { return e.Cause.Error() }

func NewApplication(
	coordinator ArchiveCoordinator,
	capture Capture,
	search SearchService,
) Application {
	return Application{coordinator: coordinator, capture: capture, search: search}
}

func (a Application) CreateArchive(
	ctx context.Context,
	key string,
	submission archive.Submission,
	raw []byte,
) (ArchiveAccepted, error) {
	if err := submission.Validate(); err != nil {
		return ArchiveAccepted{}, &ValidationError{Cause: err}
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
