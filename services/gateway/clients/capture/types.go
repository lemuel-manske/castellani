package capture

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
)

var (
	ErrInvalidResponse = errors.New("invalid capture response")
	ErrUnavailable     = errors.New("capture unavailable")
)

type Failure struct {
	Status       int
	Type         string
	Title        string
	Detail       string
	ContentRange string
}

func (f *Failure) Error() string {
	return fmt.Sprintf(
		"capture returned HTTP %d: %s",
		f.Status,
		f.Title,
	)
}

type Pagination struct {
	Limit  *int
	Cursor string
}

type Pages struct {
	Items      []json.RawMessage `json:"items"`
	NextCursor *string           `json:"nextCursor,omitempty"`
}

type Snapshot struct {
	ArchiveID   string `json:"archiveId"`
	SnapshotID  string `json:"snapshotId"`
	URL         string `json:"url"`
	FinalURL    string `json:"finalUrl,omitempty"`
	CapturedAt  string `json:"capturedAt"`
	ContentType string `json:"contentType,omitempty"`
}

type WACZOptions struct {
	MetadataOnly   bool
	Range, IfRange string
}

type WACZ struct {
	Body          io.ReadCloser
	Partial       bool
	AcceptRanges  string
	ContentRange  string
	ETag          string
	LastModified  string
	ContentLength string
}
