package application

import (
	"context"
	"errors"
	"time"

	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
	"github.com/lemuel-manske/unnamed/services/coordinator/persistence"
)

const stalledArchiveLimit = 100

func (a *Application) ReconcileStalled(ctx context.Context, age time.Duration) (int, error) {
	if age <= 0 {
		return 0, errors.New("stalled workflow age must be positive")
	}

	stalled, err := a.workflow.ListStalled(
		ctx,
		time.Now().UTC().Add(-age),
		stalledArchiveLimit,
	)

	if err != nil {
		return 0, err
	}

	reconciled := 0

	for _, archive := range stalled {
		effect, recoverable := recoveryEffect(archive)

		if !recoverable {
			continue
		}

		err := a.workflow.ScheduleRecovery(
			ctx,
			archive,
			effect,
		)

		if errors.Is(err, persistence.ErrRevisionConflict) {
			continue
		}

		if err != nil {
			return reconciled, err
		}

		reconciled++
	}

	return reconciled, nil
}

func recoveryEffect(archive domain.Archive) (domain.Effect, bool) {
	switch {
	case archive.Status == domain.StatusFinalizing && archive.Decision == domain.DecisionPublish:
		return domain.Effect{
			Type:            domain.CommandPublicationDecided,
			ArchiveID:       archive.ID,
			DecisionVersion: archive.DecisionVersion,
			PackageDigest:   archive.PackageDigest,
			ReasonCode:      "reconciliation",
		}, true
	case archive.Status == domain.StatusCompensating && archive.Decision == domain.DecisionCompensate:
		return domain.Effect{
			Type:            domain.CommandCompensationDecided,
			ArchiveID:       archive.ID,
			DecisionVersion: archive.DecisionVersion,
			ReasonCode:      "reconciliation",
		}, true
	default:
		return domain.Effect{}, false
	}
}
