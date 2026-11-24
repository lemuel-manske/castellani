package application

import (
	"context"
	"errors"

	"github.com/lemuel-manske/castellani/services/coordinator/domain"
)

func (a *Application) SubmitArchive(
	ctx context.Context,
	key string,
	submission domain.Submission,
) (AcceptedArchive, error) {
	if err := submission.Validate(); err != nil {
		return AcceptedArchive{}, SubmissionValidationError{
			cause: err,
		}
	}

	fingerprint, err := submission.Fingerprint()

	if err != nil {
		return AcceptedArchive{}, err
	}

	admission := Admission{
		Key:         key,
		Fingerprint: fingerprint,
		Submission:  submission,
	}

	accepted, err := a.repository.Admit(ctx, admission)

	if errors.Is(err, ErrIdempotencyConflict) {
		return AcceptedArchive{}, ErrIdempotencyConflict
	}

	return AcceptedArchive{
		ArchiveID: accepted.ArchiveID,
	}, err
}

func (a *Application) GetArchive(ctx context.Context, id string) (domain.Archive, error) {
	archive, err := a.repository.Find(ctx, id)

	if errors.Is(err, ErrArchiveNotFound) {
		return domain.Archive{}, ErrArchiveNotFound
	}

	return archive, err
}
