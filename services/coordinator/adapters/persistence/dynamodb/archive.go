package dynamodb

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/castellani/services/coordinator/application"
	"github.com/lemuel-manske/castellani/services/coordinator/contracts"
	"github.com/lemuel-manske/castellani/services/coordinator/domain"
)

const (
	admissionAttempts   = 5
	admissionRetryDelay = 30 * time.Millisecond
)

func (r *DynamoArchiveRepository) Admit(
	ctx context.Context,
	admission application.Admission,
) (application.AcceptedArchive, error) {
	archiveID, err := generateArchiveID()

	if err != nil {
		return application.AcceptedArchive{}, err
	}

	messageID, err := generateMessageID()

	if err != nil {
		return application.AcceptedArchive{}, err
	}

	now := time.Now().UTC()

	command := contracts.StartCrawlEnvelope{
		MessageID:     messageID,
		CorrelationID: archiveID,
		Type:          contracts.StartCrawlType,
		Version:       contracts.EnvelopeVersion,
		OccurredAt:    now.Format(time.RFC3339Nano),
		Payload: contracts.StartCrawlPayload{
			ArchiveID:      archiveID,
			SeedURL:        admission.Submission.SeedURL,
			MaxDepth:       *admission.Submission.MaxDepth,
			MaxPages:       *admission.Submission.MaxPages,
			CollectionID:   admission.Submission.CollectionID,
			AllowedOrigins: admission.Submission.AllowedOrigins,
			AuthGeneration: admission.Submission.AuthGeneration,
		},
	}

	envelope, err := json.Marshal(command)

	if err != nil {
		return application.AcceptedArchive{}, fmt.Errorf("encode StartCrawl: %w", err)
	}

	input := admissionInput{
		Key:         admission.Key,
		Fingerprint: admission.Fingerprint,
		ArchiveID:   archiveID,
		MessageID:   messageID,
		Envelope:    envelope,
		Now:         now,
		Submission:  admission.Submission,
	}

	for attempt := range admissionAttempts {
		existing, found, err := findAdmissionKey(
			ctx,
			r.client,
			admission.Key,
		)

		if err != nil {
			return application.AcceptedArchive{}, err
		}

		if found {
			if existing.fingerprint != admission.Fingerprint {
				return application.AcceptedArchive{}, application.ErrIdempotencyConflict
			}

			return application.AcceptedArchive{
				ArchiveID: existing.archiveID,
			}, nil
		}

		err = commitAdmission(
			ctx,
			r.client,
			input,
		)

		if err == nil {
			return application.AcceptedArchive{
				ArchiveID: archiveID,
			}, nil
		}

		var canceled *types.TransactionCanceledException

		if !errors.As(err, &canceled) {
			existing, found, lookupErr := findAdmissionKey(
				ctx,
				r.client,
				admission.Key,
			)

			if lookupErr == nil && found {
				if existing.fingerprint != admission.Fingerprint {
					return application.AcceptedArchive{}, application.ErrIdempotencyConflict
				}

				return application.AcceptedArchive{
					ArchiveID: existing.archiveID,
				}, nil
			}

			return application.AcceptedArchive{}, fmt.Errorf("admit archive: %w", err)
		}

		delay := time.Duration(attempt+1) * admissionRetryDelay
		timer := time.NewTimer(delay)

		select {
		case <-ctx.Done():
			timer.Stop()

			return application.AcceptedArchive{}, ctx.Err()
		case <-timer.C:
		}
	}

	return application.AcceptedArchive{}, errors.New("archive admission contention exceeded retry budget")
}

func (r *DynamoArchiveRepository) Find(
	ctx context.Context,
	id string,
) (domain.Archive, error) {
	archive, found, err := getArchive(
		ctx,
		r.client,
		id,
	)

	if err != nil {
		return domain.Archive{}, err
	}

	if !found {
		return domain.Archive{}, application.ErrArchiveNotFound
	}

	return archive, nil
}

func (r *DynamoArchiveRepository) CommitEvent(
	ctx context.Context,
	before domain.Archive,
	after domain.Archive,
	event domain.Event,
	effects []domain.Effect,
) error {
	err := commitEvent(
		ctx,
		r.client,
		eventCommitInput{
			Before:  before,
			After:   after,
			Event:   event,
			Effects: effects,
			Now:     time.Now().UTC(),
		},
	)

	if err == nil {
		return nil
	}

	var canceled *types.TransactionCanceledException

	if !errors.As(err, &canceled) {
		return fmt.Errorf("commit archive event: %w", err)
	}

	processed, err := inboxHasMessage(
		ctx,
		r.client,
		event.MessageID,
	)

	if err != nil {
		return err
	}

	if processed {
		return application.ErrAlreadyProcessed
	}

	return application.ErrRevisionConflict
}

func (r *DynamoArchiveRepository) ListStalled(
	ctx context.Context,
	before time.Time,
	limit int,
) ([]domain.Archive, error) {
	if limit < 1 {
		return nil, errors.New("stalled archive limit must be positive")
	}

	recoveries := []string{
		domain.DecisionPublish,
		domain.DecisionCompensate,
	}

	archives := make(
		[]domain.Archive,
		0,
		limit,
	)

	for _, recovery := range recoveries {
		found, err := listStalledArchives(
			ctx,
			r.client,
			recovery,
			before,
			limit-len(archives),
		)

		if err != nil {
			return nil, err
		}

		archives = append(archives, found...)

		if len(archives) == limit {
			break
		}
	}

	return archives, nil
}

func (r *DynamoArchiveRepository) ScheduleRecovery(
	ctx context.Context,
	archive domain.Archive,
	effect domain.Effect,
) error {
	now := time.Now().UTC()
	messageID, err := generateRecoveryID()

	if err != nil {
		return err
	}

	envelope, err := encodeEffect(
		messageID,
		effect,
		now,
	)

	if err != nil {
		return err
	}

	err = commitRecovery(
		ctx,
		r.client,
		recoveryCommitInput{
			Archive:   archive,
			Effect:    effect,
			MessageID: messageID,
			Envelope:  envelope,
			Now:       now,
		},
	)

	if err == nil {
		return nil
	}

	var canceled *types.TransactionCanceledException

	if errors.As(err, &canceled) {
		return application.ErrRevisionConflict
	}

	return fmt.Errorf("schedule archive recovery: %w", err)
}

func recoveryKey(archive domain.Archive) string {
	if archive.Status == domain.StatusFinalizing && archive.Decision == domain.DecisionPublish {
		return domain.DecisionPublish
	}

	if archive.Status == domain.StatusCompensating && archive.Decision == domain.DecisionCompensate {
		return domain.DecisionCompensate
	}

	return domain.DecisionNone
}
