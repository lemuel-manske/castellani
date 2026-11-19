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
type SessionRequest struct{ ArchiveID, TargetURL string }

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

type Session struct {
	SessionID      string `json:"sessionId"`
	ArchiveID      string `json:"archiveId"`
	Status         string `json:"status"`
	ExpiresAt      string `json:"expiresAt"`
	AuthGeneration *int   `json:"authGeneration,omitempty"`
}

type WACZOptions struct {
	MetadataOnly   bool
	Range, IfRange string
}
type WACZ struct {
	Body                                                          io.ReadCloser
	Partial                                                       bool
	AcceptRanges, ContentRange, ETag, LastModified, ContentLength string
}
