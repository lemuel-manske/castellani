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

type ArchiveCoordinator interface {
	CreateArchive(context.Context, string, []byte) (archive.Accepted, error)
	GetArchive(context.Context, string) (json.RawMessage, error)
}

type Application struct {
	Coordinator ArchiveCoordinator
	capture     Capture
	search      SearchService
}

type ValidationError struct{ Cause error }

func (e *ValidationError) Error() string { return e.Cause.Error() }

func NewApplication(coordinator ArchiveCoordinator) Application {
	return NewApplicationWithServices(coordinator, nil, nil)
}

func NewApplicationWithServices(coordinator ArchiveCoordinator, capture Capture, search SearchService) Application {
	return Application{Coordinator: coordinator, capture: capture, search: search}
}

func (a Application) CreateArchive(ctx context.Context, key string, submission archive.Submission, raw []byte) (archive.Accepted, error) {
	if err := submission.Validate(); err != nil {
		return archive.Accepted{}, &ValidationError{Cause: err}
	}
	return a.Coordinator.CreateArchive(ctx, key, raw)
}

func (a Application) GetArchive(ctx context.Context, id string) (json.RawMessage, error) {
	if !httpx.ValidPathSegment(id) {
		return nil, ErrInvalidArchiveID
	}
	return a.Coordinator.GetArchive(ctx, id)
}
