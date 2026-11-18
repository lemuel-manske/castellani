// Package application orchestrates the gateway use cases independently of HTTP routing.
package application

import (
	"context"
	"encoding/json"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/archive"
)

type ArchiveCoordinator interface {
	Admit(context.Context, string, []byte) (archive.Accepted, error)
	Status(context.Context, string) (json.RawMessage, error)
}

type Application struct {
	Coordinator ArchiveCoordinator
}

func NewApplication(coordinator ArchiveCoordinator) Application {
	return Application{Coordinator: coordinator}
}

func (a Application) CreateArchive(ctx context.Context, key string, request []byte) (archive.Accepted, error) {
	return a.Coordinator.Admit(ctx, key, request)
}

func (a Application) GetArchive(ctx context.Context, id string) (json.RawMessage, error) {
	return a.Coordinator.Status(ctx, id)
}
