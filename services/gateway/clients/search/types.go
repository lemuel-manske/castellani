package search

import (
	"encoding/json"
	"errors"
	"fmt"
)

var (
	ErrInvalidResponse = errors.New("invalid search response")
	ErrUnavailable     = errors.New("search unavailable")
)

type Failure struct {
	Status              int
	Type, Title, Detail string
}

func (f *Failure) Error() string {
	return fmt.Sprintf(
		"search returned HTTP %d: %s",
		f.Status,
		f.Title,
	)
}

type Pagination struct {
	Limit  *int
	Cursor string
}
type Query struct {
	Text, CollectionID, ArchiveID, SnapshotID, CapturedFrom, CapturedTo string
	Pagination                                                          Pagination
}
type Results struct {
	Results    []json.RawMessage `json:"results"`
	NextCursor *string           `json:"nextCursor,omitempty"`
}
