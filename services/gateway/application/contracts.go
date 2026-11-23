package application

import (
	"context"
	"encoding/json"
	"io"
)

type Pagination struct {
	Limit  *int
	Cursor string
}

type SearchQuery struct {
	Text         string
	CollectionID string
	ArchiveID    string
	SnapshotID   string
	CapturedFrom string
	CapturedTo   string
	Pagination   Pagination
}

type SessionRequest struct {
	ArchiveID string `json:"archiveId"`
	TargetURL string `json:"targetUrl"`
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

type SearchResults struct {
	Results    []json.RawMessage `json:"results"`
	NextCursor *string           `json:"nextCursor,omitempty"`
}

type ArchiveAccepted struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	StatusURL string `json:"statusUrl"`
}

type Capture interface {
	ListPages(
		context.Context,
		string,
		Pagination,
	) (Pages, error)

	GetSnapshot(
		context.Context,
		string,
		string,
	) (Snapshot, error)

	GetWACZ(
		context.Context,
		string,
		WACZOptions,
	) (WACZ, error)

	CreateSession(
		context.Context,
		string,
		SessionRequest,
		[]byte,
	) (Session, error)

	GetSession(context.Context, string) (Session, error)

	UpdateSession(
		context.Context,
		string,
		[]byte,
	) (Session, error)
}

type Search interface {
	Search(context.Context, SearchQuery) (SearchResults, error)
}

type Coordinator interface {
	CreateArchive(
		context.Context,
		string,
		[]byte,
	) (ArchiveAccepted, error)

	GetArchive(context.Context, string) (json.RawMessage, error)
}
