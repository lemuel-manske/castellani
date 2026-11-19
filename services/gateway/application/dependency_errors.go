package application

import (
	"errors"
	"fmt"
)

var (
	ErrInvalidUpstream       = errors.New("invalid upstream response")
	ErrDependencyUnavailable = errors.New("dependency unavailable")
	ErrInvalidPagination     = errors.New("invalid pagination")
	ErrInvalidSearch         = errors.New("invalid search")
	ErrInvalidSession        = errors.New("invalid session")
	ErrInvalidSessionID      = errors.New("invalid session ID")
	ErrInvalidSnapshotID     = errors.New("invalid snapshot ID")
	ErrInvalidWACZRange      = errors.New("invalid WACZ range")
)

type DependencyFailure struct {
	Status                            int
	Type, Title, Detail, ContentRange string
}

func (e *DependencyFailure) Error() string {
	return fmt.Sprintf("dependency returned HTTP %d: %s", e.Status, e.Title)
}
