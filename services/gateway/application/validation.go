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

func (s Submission) Validate() error {
	if !httpx.ValidHTTPURL(s.SeedURL) {
		return fmt.Errorf("%w: seedUrl must be an absolute HTTP(S) URL without credentials or fragment", ErrInvalidSubmission)
	}

	if s.MaxDepth == nil || *s.MaxDepth < 0 {
		return fmt.Errorf("%w: maxDepth must be a nonnegative integer", ErrInvalidSubmission)
	}

	if s.MaxPages == nil || *s.MaxPages < 1 {
		return fmt.Errorf("%w: maxPages must be a positive integer", ErrInvalidSubmission)
	}

	if s.AuthGeneration != nil && *s.AuthGeneration < 1 {
		return fmt.Errorf("%w: authGeneration must be a positive integer", ErrInvalidSubmission)
	}

	seen := make(map[string]struct{}, len(s.AllowedOrigins))
	for _, origin := range s.AllowedOrigins {
		if !httpx.ValidHTTPURL(origin) {
			return fmt.Errorf("%w: allowedOrigins entries must be absolute HTTP(S) URLs without credentials or fragment", ErrInvalidSubmission)
		}

		if _, exists := seen[origin]; exists {
			return fmt.Errorf("%w: allowedOrigins entries must be unique", ErrInvalidSubmission)
		}
		seen[origin] = struct{}{}
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
