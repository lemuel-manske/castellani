package application

import (
	"context"
)

func (a Application) ListPages(
	ctx context.Context,
	archiveID string,
	pagination Pagination,
) (Pages, error) {
	if err := validateArchiveID(archiveID); err != nil {
		return Pages{}, err
	}

	if err := pagination.Validate(); err != nil {
		return Pages{}, err
	}

	if a.capture == nil {
		return Pages{}, ErrDependencyUnavailable
	}
	return a.capture.ListPages(
		ctx,
		archiveID,
		pagination,
	)
}

func (a Application) GetSnapshot(ctx context.Context, archiveID, snapshotID string) (Snapshot, error) {
	if err := validateArchiveID(archiveID); err != nil {
		return Snapshot{}, err
	}

	if err := validateSnapshotID(snapshotID); err != nil {
		return Snapshot{}, err
	}

	if a.capture == nil {
		return Snapshot{}, ErrDependencyUnavailable
	}
	return a.capture.GetSnapshot(
		ctx,
		archiveID,
		snapshotID,
	)
}

func (a Application) GetWACZ(
	ctx context.Context,
	archiveID string,
	options WACZOptions,
) (WACZ, error) {
	if err := validateArchiveID(archiveID); err != nil {
		return WACZ{}, err
	}

	if err := options.Validate(); err != nil {
		return WACZ{}, err
	}

	if a.capture == nil {
		return WACZ{}, ErrDependencyUnavailable
	}
	return a.capture.GetWACZ(
		ctx,
		archiveID,
		options,
	)
}
