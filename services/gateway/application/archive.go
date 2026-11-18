// Package application orchestrates Gateway use cases independently of HTTP routing.
package application

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/archive"
)

type ArchiveCoordinator interface {
	Admit(context.Context, string, []byte) (archive.Accepted, error)
	Status(context.Context, string) (json.RawMessage, error)
}

type Application struct {
	Coordinator ArchiveCoordinator
}

type ValidationError struct {
	Cause error
}

func (e *ValidationError) Error() string {
	return e.Cause.Error()
}

var ErrInvalidArchiveID = errors.New("archive ID must be a nonempty path segment")

func NewApplication(coordinator ArchiveCoordinator) Application {
	return Application{Coordinator: coordinator}
}

func (a Application) CreateArchive(ctx context.Context, key string, submission archive.Submission, raw []byte) (archive.Accepted, error) {

	if err := submission.Validate(); err != nil {
		return archive.Accepted{}, &ValidationError{Cause: err}
	}
	return a.Coordinator.Admit(ctx, key, raw)
}

func (a Application) GetArchive(ctx context.Context, id string) (json.RawMessage, error) {

	if !archive.ValidID(id) {
		return nil, ErrInvalidArchiveID
	}
	return a.Coordinator.Status(ctx, id)
}
