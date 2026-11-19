package application

import (
 "context"
 "encoding/json"
 "io"
)

type Pagination struct { Limit *int; Cursor string }
type SearchQuery struct {
 Text, CollectionID, ArchiveID, SnapshotID, CapturedFrom, CapturedTo string
 Pagination Pagination
}
type SessionRequest struct {
 ArchiveID string `json:"archiveId"`
 TargetURL string `json:"targetUrl"`
}
type WACZOptions struct { MetadataOnly bool; Range, IfRange string }
type WACZ struct {
 Body io.ReadCloser
 Partial bool
 AcceptRanges, ContentRange, ETag, LastModified, ContentLength string
}
type Capture interface {
 ListPages(context.Context, string, Pagination) (json.RawMessage, error)
 GetSnapshot(context.Context, string, string) (json.RawMessage, error)
 GetWACZ(context.Context, string, WACZOptions) (WACZ, error)
 CreateSession(context.Context, string, SessionRequest, []byte) (json.RawMessage, error)
 GetSession(context.Context, string) (json.RawMessage, error)
 UpdateSession(context.Context, string, []byte) (json.RawMessage, error)
}
type SearchService interface {
 Search(context.Context, SearchQuery) (json.RawMessage, error)
}
