// Package application implements Coordinator use cases through technology-independent ports.
package application

import (
	"context"
	"errors"
	"time"

	"github.com/lemuel-manske/castellani/services/coordinator/domain"
)

var (
	ErrInvalidSubmission   = errors.New("invalid archive submission")
	ErrIdempotencyConflict = errors.New("idempotency key belongs to another submission")
	ErrArchiveNotFound     = errors.New("archive not found")
	ErrRevisionConflict    = errors.New("archive changed concurrently")
	ErrAlreadyProcessed    = errors.New("event already processed")
)

type Admission struct {
	Key         string
	Fingerprint string
	Submission  domain.Submission
}

type AcceptedArchive struct {
	ArchiveID string
}

type Message struct {
	ID      string
	Type    string
	Payload []byte
	Lease   string
}

type ArchiveRepository interface {
	Admit(context.Context, Admission) (AcceptedArchive, error)

	Find(context.Context, string) (domain.Archive, error)

	CommitEvent(
		context.Context,
		domain.Archive,
		domain.Archive,
		domain.Event,
		[]domain.Effect,
	) error

	ListStalled(
		context.Context,
		time.Time,
		int,
	) ([]domain.Archive, error)

	ScheduleRecovery(
		context.Context,
		domain.Archive,
		domain.Effect,
	) error
}

type Outbox interface {
	Claim(context.Context, time.Duration) (Message, bool, error)

	Confirm(context.Context, Message) error
}

type Publisher interface {
	Publish(context.Context, Message) error
}

type SubmissionValidationError struct {
	cause error
}

func (e SubmissionValidationError) Error() string {
	return e.cause.Error()
}

func (e SubmissionValidationError) Unwrap() []error {
	return []error{ErrInvalidSubmission, e.cause}
}

type Application struct {
	repository ArchiveRepository
}

func NewApplication(repository ArchiveRepository) *Application {
	return &Application{
		repository: repository,
	}
}
