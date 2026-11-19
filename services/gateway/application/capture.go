package application

import (
	"context"
	"encoding/json"
)

func (a Application) ListPages(
	ctx context.Context,
	archiveID string,
	pagination Pagination,
) (json.RawMessage, error) {
	if err := validateArchiveID(archiveID); err != nil {
		return nil, err
	}

	if err := pagination.Validate(); err != nil {
		return nil, err
	}

	if a.capture == nil {
		return nil, ErrDependencyUnavailable
	}
	return a.capture.ListPages(
		ctx,
		archiveID,
		pagination,
	)
}

func (a Application) GetSnapshot(ctx context.Context, archiveID, snapshotID string) (json.RawMessage, error) {
	if err := validateArchiveID(archiveID); err != nil {
		return nil, err
	}

	if err := validateSnapshotID(snapshotID); err != nil {
		return nil, err
	}

	if a.capture == nil {
		return nil, ErrDependencyUnavailable
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
