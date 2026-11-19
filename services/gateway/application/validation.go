package application

import (
	"fmt"
	"strings"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
)

const (
	maxLimit            = 100
	maxQueryLength      = 500
	maxRangeHeaderBytes = 256
)

func (p Pagination) Validate() error {
	if p.Limit != nil && (*p.Limit < 1 || *p.Limit > maxLimit) {
		return fmt.Errorf("%w: limit must be between 1 and 100", ErrInvalidPagination)
	}

	return nil
}

func (q SearchQuery) Validate() error {
	if len(q.Text) == 0 || len(q.Text) > maxQueryLength || strings.TrimSpace(q.Text) == "" {
		return fmt.Errorf("%w: q must contain between 1 and 500 characters", ErrInvalidSearch)
	}

	if err := q.Pagination.Validate(); err != nil {
		return fmt.Errorf(
			"%w: %v",
			ErrInvalidSearch,
			err,
		)
	}

	var from, to time.Time
	var hasFrom, hasTo bool
	for _, v := range []struct {
		name, raw string
	}{
		{"capturedFrom", q.CapturedFrom},
		{"capturedTo", q.CapturedTo},
	} {
		if v.raw == "" {
			continue
		}
		parsed, err := time.Parse(time.RFC3339, v.raw)

		if err != nil {
			return fmt.Errorf(
				"%w: %s must be RFC3339",
				ErrInvalidSearch,
				v.name,
			)
		}

		if v.name == "capturedFrom" {
			from = parsed
			hasFrom = true
		} else {
			to = parsed
			hasTo = true
		}
	}

	if hasFrom && hasTo && from.After(to) {
		return fmt.Errorf("%w: capturedFrom must not exceed capturedTo", ErrInvalidSearch)
	}

	return nil
}

func (s SessionRequest) Validate() error {
	if !httpx.ValidPathSegment(s.ArchiveID) || !httpx.ValidHTTPURL(s.TargetURL) {
		return fmt.Errorf("%w: expected archiveId and absolute HTTP(S) targetUrl", ErrInvalidSession)
	}

	return nil
}

func (o WACZOptions) Validate() error {
	invalidRange := len(o.Range) > maxRangeHeaderBytes || strings.ContainsAny(o.Range, "\r\n,")
	invalidIfRange := len(o.IfRange) > maxRangeHeaderBytes || strings.ContainsAny(o.IfRange, "\r\n")

	if invalidRange || invalidIfRange {
		return fmt.Errorf("%w: only one valid byte range is supported", ErrInvalidWACZRange)
	}

	return nil
}

func validateArchiveID(id string) error {
	if !httpx.ValidPathSegment(id) {
		return ErrInvalidArchiveID
	}

	return nil
}

func validateSessionID(id string) error {
	if !httpx.ValidPathSegment(id) {
		return ErrInvalidSessionID
	}

	return nil
}

func validateSnapshotID(id string) error {
	if !httpx.ValidPathSegment(id) {
		return ErrInvalidSnapshotID
	}

	return nil
}
