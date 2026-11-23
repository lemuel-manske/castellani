// Package application implements Coordinator use cases through technology-independent ports.
package application

import (
	"errors"

	"github.com/lemuel-manske/castellani/services/coordinator/persistence"
)

var (
	ErrInvalidSubmission   = errors.New("invalid archive submission")
	ErrIdempotencyConflict = errors.New("idempotency key belongs to another submission")
	ErrArchiveNotFound     = errors.New("archive not found")
)

type SubmissionValidationError struct {
	cause error
}

func (e SubmissionValidationError) Error() string {
	return e.cause.Error()
}

func (e SubmissionValidationError) Unwrap() []error {
	return []error{ErrInvalidSubmission, e.cause}
}

type AcceptedArchive struct {
	ArchiveID string
}

type Application struct {
	repository persistence.ArchiveRepository
}

func NewApplication(repository persistence.ArchiveRepository) *Application {
	return &Application{
		repository: repository,
	}
}
