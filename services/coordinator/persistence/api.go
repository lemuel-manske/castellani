// Package persistence defines the Coordinator's durable storage contracts.
package persistence

import (
	"context"
	"errors"
	"time"

	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
)

var (
	ErrArchiveNotFound     = errors.New("archive not found")
	ErrIdempotencyConflict = errors.New("idempotency key belongs to another submission")
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
