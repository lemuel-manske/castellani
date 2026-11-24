package assembly

import (
	"context"
	"errors"

	"github.com/lemuel-manske/castellani/services/gateway/application"
	"github.com/lemuel-manske/castellani/services/gateway/clients/capture"
)

type captureAdapter struct {
	client *capture.Client
}

func (a captureAdapter) ListPages(
	ctx context.Context,
	archiveID string,
	page application.Pagination,
) (application.Pages, error) {
	result, err := a.client.ListPages(
		ctx,
		archiveID,
		capture.Pagination{
			Limit:  page.Limit,
			Cursor: page.Cursor,
		},
	)

	if err != nil {
		return application.Pages{}, captureError(err)
	}

	return application.Pages{
		Items:      result.Items,
		NextCursor: result.NextCursor,
	}, nil
}

func (a captureAdapter) GetSnapshot(ctx context.Context, archiveID, snapshotID string) (application.Snapshot, error) {
	result, err := a.client.GetSnapshot(
		ctx,
		archiveID,
		snapshotID,
	)

	if err != nil {
		return application.Snapshot{}, captureError(err)
	}

	return application.Snapshot{
		ArchiveID:   result.ArchiveID,
		SnapshotID:  result.SnapshotID,
		URL:         result.URL,
		FinalURL:    result.FinalURL,
		CapturedAt:  result.CapturedAt,
		ContentType: result.ContentType,
	}, nil
}

func (a captureAdapter) GetWACZ(
	ctx context.Context,
	archiveID string,
	options application.WACZOptions,
) (application.WACZ, error) {
	result, err := a.client.GetWACZ(
		ctx,
		archiveID,
		capture.WACZOptions{
			MetadataOnly: options.MetadataOnly,
			Range:        options.Range,
			IfRange:      options.IfRange,
		},
	)

	if err != nil {
		return application.WACZ{}, captureError(err)
	}

	return application.WACZ{
		Body:          result.Body,
		Partial:       result.Partial,
		AcceptRanges:  result.AcceptRanges,
		ContentRange:  result.ContentRange,
		ETag:          result.ETag,
		LastModified:  result.LastModified,
		ContentLength: result.ContentLength,
	}, nil
}

func captureError(err error) error {
	var failure *capture.Failure
	switch {
	case errors.Is(err, capture.ErrInvalidResponse):
		return application.ErrInvalidUpstream
	case errors.Is(err, capture.ErrUnavailable):
		return errUnavailable(err)
	case errors.As(err, &failure):
		return &application.DependencyFailure{
			Status:       failure.Status,
			Type:         failure.Type,
			Title:        failure.Title,
			Detail:       failure.Detail,
			ContentRange: failure.ContentRange,
		}
	default:
		return errUnavailable(err)
	}
}
