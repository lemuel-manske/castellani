// Package application implements Coordinator use cases through technology-independent ports.
package application

import (
	"errors"

	"github.com/lemuel-manske/unnamed/services/coordinator/persistence"
)

var (
	ErrInvalidSubmission     = errors.New("invalid archive submission")
	ErrInvalidIdempotencyKey = errors.New("invalid idempotency key")
	ErrIdempotencyConflict   = errors.New("idempotency key belongs to another submission")
	ErrArchiveNotFound       = errors.New("archive not found")
	ErrInvalidArchiveID      = errors.New("invalid archive ID")
)

type Application struct {
	archives persistence.ArchiveRepository
	workflow persistence.WorkflowRepository
}

func NewApplication(archives persistence.ArchiveRepository, workflow persistence.WorkflowRepository) *Application {
	return &Application{
		archives: archives,
		workflow: workflow,
	}
}
