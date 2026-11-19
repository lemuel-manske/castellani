package application

import (
	"context"
	"errors"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
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

	admission := Admission{
		Key:         key,
		Fingerprint: fingerprint,
		Submission:  submission,
	}

	return a.archives.Admit(ctx, admission)
}

func (a *Application) GetArchive(ctx context.Context, id string) (domain.Archive, error) {
	if !httpx.ValidPathSegment(id) {
		return domain.Archive{}, ErrInvalidArchiveID
	}

	return a.archives.Find(ctx, id)
}
