// Package application implements Coordinator use cases through technology-independent ports.
package application

import (
	"context"
	"errors"
	"time"

	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
)

var (
	ErrInvalidSubmission     = errors.New("invalid archive submission")
	ErrInvalidIdempotencyKey = errors.New("invalid idempotency key")
	ErrIdempotencyConflict   = errors.New("idempotency key belongs to another submission")
	ErrArchiveNotFound       = errors.New("archive not found")
	ErrInvalidArchiveID      = errors.New("invalid archive ID")
)

type Application struct {
	archives ArchiveRepository
	workflow WorkflowRepository
}

func NewApplication(archives ArchiveRepository, workflow WorkflowRepository) *Application {
	return &Application{
		archives: archives,
		workflow: workflow,
	}
}

type Admission struct {
	Key         string
	Fingerprint string
	Submission  domain.Submission
}

type Message struct {
	ID      string
	Type    string
	Payload []byte
	Lease   string
}

type AcceptedArchive struct {
	ArchiveID string
}

type Outbox interface {
	Claim(context.Context, time.Duration) (Message, bool, error)

	Confirm(context.Context, Message) error
}

type Publisher interface {
	Publish(context.Context, Message) error
}

type Dispatcher struct {
	outbox    Outbox
	publisher Publisher
}

type ArchiveRepository interface {
	Admit(context.Context, Admission) (AcceptedArchive, error)

	Find(context.Context, string) (domain.Archive, error)
}

type WorkflowRepository interface {
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

func NewDispatcher(outbox Outbox, publisher Publisher) *Dispatcher {
	return &Dispatcher{
		outbox:    outbox,
		publisher: publisher,
	}
}
