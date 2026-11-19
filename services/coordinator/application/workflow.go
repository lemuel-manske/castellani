package application

import (
	"context"
	"errors"

	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
	"github.com/lemuel-manske/unnamed/services/coordinator/persistence"
)

const eventCommitAttempts = 8

func (a *Application) HandleEvent(ctx context.Context, event domain.Event) error {
	if event.MessageID == "" || event.ArchiveID == "" {
		return domain.ErrInvalidEvent
	}

	for range eventCommitAttempts {
		current, err := a.workflow.Find(ctx, event.ArchiveID)

		if err != nil {
			return err
		}

		next, effects, err := domain.Apply(current, event)

		if err != nil {
			return err
		}

		err = a.workflow.CommitEvent(
			ctx,
			current,
			next,
			event,
			effects,
		)

		switch {
		case err == nil, errors.Is(err, persistence.ErrAlreadyProcessed):
			return nil
		case errors.Is(err, persistence.ErrRevisionConflict):
			continue
		default:
			return err
		}
	}

	return persistence.ErrRevisionConflict
}
