package application

import (
	"errors"
	"fmt"
)

var (
	ErrArchiveNotPublished   = errors.New("archive is not published")
	ErrDependencyUnavailable = errors.New("dependency unavailable")
	ErrInvalidUpstream       = errors.New("invalid upstream response")
)

type DependencyFailure struct {
	Status                            int
	Type, Title, Detail, ContentRange string
}

func (e *DependencyFailure) Error() string {
	return fmt.Sprintf(
		"dependency returned HTTP %d: %s",
		e.Status,
		e.Title,
	)
}
