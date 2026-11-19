package application

import (
	"context"
	"errors"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
	"github.com/lemuel-manske/unnamed/services/coordinator/persistence"
)

func (a *Application) SubmitArchive(
	ctx context.Context,
	key string,
	submission domain.Submission,
) (AcceptedArchive, error) {
	if !httpx.ValidIdempotencyKey(key) {
		return AcceptedArchive{}, ErrInvalidIdempotencyKey
	}

	if err := submission.Validate(); err != nil {
		return AcceptedArchive{}, errors.Join(ErrInvalidSubmission, err)
	}

	fingerprint, err := submission.Fingerprint()

	if err != nil {
		return AcceptedArchive{}, err
	}

	admission := persistence.Admission{
		Key:         key,
		Fingerprint: fingerprint,
		Submission:  submission,
	}

	accepted, err := a.archives.Admit(ctx, admission)

	if errors.Is(err, persistence.ErrIdempotencyConflict) {
		return AcceptedArchive{}, ErrIdempotencyConflict
	}

	return AcceptedArchive{ArchiveID: accepted.ArchiveID}, err
}

func (a *Application) GetArchive(ctx context.Context, id string) (domain.Archive, error) {
	if !httpx.ValidPathSegment(id) {
		return domain.Archive{}, ErrInvalidArchiveID
	}

	archive, err := a.archives.Find(ctx, id)

	if errors.Is(err, persistence.ErrArchiveNotFound) {
		return domain.Archive{}, ErrArchiveNotFound
	}

	return archive, err
}
