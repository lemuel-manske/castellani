// Package capture implements the Capture service client.
package capture

import (
 "bytes"
 "context"
 "encoding/json"
 "fmt"
 "io"
 "net/http"
 "net/url"
 "strconv"
 "time"

 "github.com/lemuel-manske/castellani/libs/httpx"
 "github.com/lemuel-manske/unnamed/services/gateway/application"
 "github.com/lemuel-manske/unnamed/services/gateway/common"
)
const (
 maxJSONBytes = 1 << 20
 defaultStreamTimeout = 30 * time.Minute
)
type Client struct { origin url.URL; http, stream *http.Client }
func NewClient(origin url.URL, timeout, streamTimeout time.Duration) *Client {
 transport := &http.Transport{Proxy: http.ProxyFromEnvironment, ResponseHeaderTimeout: timeout, IdleConnTimeout: 90*time.Second, MaxIdleConnsPerHost: 16}
 noRedirect := func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
 if streamTimeout <= 0 { streamTimeout = defaultStreamTimeout }
 return &Client{origin: origin,
  http: &http.Client{Timeout: timeout, CheckRedirect: noRedirect, Transport: transport},
  stream: &http.Client{Timeout: streamTimeout, CheckRedirect: noRedirect, Transport: transport},
 }
}
func (c *Client) ListPages(ctx context.Context, archiveID string, page application.Pagination) (json.RawMessage, error) {
 query := url.Values{}
 if page.Limit != nil { query.Set("limit", strconv.Itoa(*page.Limit)) }
 if page.Cursor != "" { query.Set("cursor", page.Cursor) }
 path := common.ArchivePathPrefix + url.PathEscape(archiveID) + common.PagesPathSuffix
 data, err := c.json(ctx, http.MethodGet, path, query.Encode(), "", nil, http.StatusOK)
 if err != nil { return nil, err }
 var v struct { Items []json.RawMessage `json:"items"` }
 if json.Unmarshal(data, &v) != nil || v.Items == nil { return nil, application.ErrInvalidUpstream }
 return data, nil
}
func (c *Client) GetSnapshot(ctx context.Context, archiveID, snapshotID string) (json.RawMessage, error) {
 path := common.ArchivePathPrefix + url.PathEscape(archiveID) + common.SnapshotPathSegment + url.PathEscape(snapshotID)
 data, err := c.json(ctx, http.MethodGet, path, "", "", nil, http.StatusOK)
 if err != nil { return nil, err }
 var v struct { ArchiveID string `json:"archiveId"`; SnapshotID string `json:"snapshotId"`; URL string `json:"url"`; CapturedAt string `json:"capturedAt"` }
 if json.Unmarshal(data, &v) != nil || v.ArchiveID != archiveID || v.SnapshotID != snapshotID || v.URL == "" || v.CapturedAt == "" {
  return nil, application.ErrInvalidUpstream
 }
 return data, nil
}
func (c *Client) CreateSession(ctx context.Context, key string, session application.SessionRequest, raw []byte) (json.RawMessage, error) {
 data, err := c.json(ctx, http.MethodPost, common.SessionsPath, "", key, raw, http.StatusCreated)
 if err != nil { return nil, err }
 if err := validateSession(data, "", session.ArchiveID); err != nil { return nil, err }
 return data, nil
}
func (c *Client) GetSession(ctx context.Context, id string) (json.RawMessage, error) {
 return c.session(ctx, http.MethodGet, id, nil)
}
func (c *Client) UpdateSession(ctx context.Context, id, status string, raw []byte) (json.RawMessage, error) {
 return c.session(ctx, http.MethodPut, id, raw)
}
func (c *Client) session(ctx context.Context, method, id string, raw []byte) (json.RawMessage, error) {
 data, err := c.json(ctx, method, common.SessionPathPrefix+url.PathEscape(id), "", "", raw, http.StatusOK)
 if err != nil { return nil, err }
 if err := validateSession(data, id, ""); err != nil { return nil, err }
 return data, nil
}
func validateSession(data []byte, id, archiveID string) error {
 var v struct { SessionID string `json:"sessionId"`; ArchiveID string `json:"archiveId"`; Status string `json:"status"`; ExpiresAt string `json:"expiresAt"` }
 if json.Unmarshal(data, &v) != nil || !httpx.ValidPathSegment(v.SessionID) || !httpx.ValidPathSegment(v.ArchiveID) ||
  v.Status == "" || v.ExpiresAt == "" || (id != "" && v.SessionID != id) || (archiveID != "" && v.ArchiveID != archiveID) {
  return application.ErrInvalidUpstream
 }
 return nil
}
func (c *Client) GetWACZ(ctx context.Context, id string, options application.WACZOptions) (application.WACZ, error) {
 method := http.MethodGet
 if options.MetadataOnly { method = http.MethodHead }
 path := common.ArchivePathPrefix + url.PathEscape(id) + common.WACZPathSuffix
 request, err := c.request(ctx, method, path, "", nil)
 if err != nil { return application.WACZ{}, err }
 if options.Range != "" { request.Header.Set("Range", options.Range) }
 if options.IfRange != "" { request.Header.Set("If-Range", options.IfRange) }
 response, err := c.stream.Do(request)
 if err != nil { return application.WACZ{}, fmt.Errorf("%w: capture WACZ: %v", application.ErrDependencyUnavailable, err) }
 if response.StatusCode == http.StatusNotFound || response.StatusCode == http.StatusServiceUnavailable || response.StatusCode == http.StatusRequestedRangeNotSatisfiable {
  defer response.Body.Close()
  data, err := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))
  if err != nil || len(data) > maxJSONBytes { return application.WACZ{}, application.ErrInvalidUpstream }
  failure, err := parseFailure(response.StatusCode, data)
  if err != nil { return application.WACZ{}, err }
  failure.ContentRange = response.Header.Get("Content-Range")
  return application.WACZ{}, failure
 }
 success := response.StatusCode == http.StatusOK || response.StatusCode == http.StatusPartialContent
 if !success || response.Header.Get(httpx.HeaderContentType) != httpx.WACZMediaType {
  response.Body.Close()
  return application.WACZ{}, application.ErrInvalidUpstream
 }
 return application.WACZ{Body: response.Body, Partial: response.StatusCode == http.StatusPartialContent,
  AcceptRanges: response.Header.Get("Accept-Ranges"), ContentRange: response.Header.Get("Content-Range"),
  ETag: response.Header.Get("ETag"), LastModified: response.Header.Get("Last-Modified"),
  ContentLength: response.Header.Get("Content-Length")}, nil
}
func (c *Client) json(ctx context.Context, method, path, query, key string, body []byte, success int) (json.RawMessage, error) {
 request, err := c.request(ctx, method, path, query, body)
 if err != nil { return nil, err }
 if body != nil { request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON) }
 if key != "" { request.Header.Set(httpx.IdempotencyHeader, key) }
 response, err := c.http.Do(request)
 if err != nil { return nil, fmt.Errorf("%w: capture request: %v", application.ErrDependencyUnavailable, err) }
 defer response.Body.Close()
 data, err := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))
 if err != nil { return nil, fmt.Errorf("%w: read capture: %v", application.ErrDependencyUnavailable, err) }
 if len(data) > maxJSONBytes { return nil, application.ErrInvalidUpstream }
 if response.StatusCode != success { return nil, failureError(response.StatusCode, data) }
 if !json.Valid(data) || bytes.Equal(bytes.TrimSpace(data), []byte("null")) { return nil, application.ErrInvalidUpstream }
 return data, nil
}
func (c *Client) request(ctx context.Context, method, path, query string, body []byte) (*http.Request, error) {
 target := c.origin; target.Path = path; target.RawPath = ""; target.RawQuery = query
 return http.NewRequestWithContext(ctx, method, target.String(), bytes.NewReader(body))
}
func failureError(status int, data []byte) error {
 failure, err := parseFailure(status, data)
 if err != nil { return err }
 return failure
}
func parseFailure(status int, data []byte) (*application.DependencyFailure, error) {
 switch status {
 case 400, 401, 403, 404, 409, 416, 422, 503:
 default: return nil, application.ErrInvalidUpstream
 }
 var p httpx.Problem
 if json.Unmarshal(data, &p) != nil || p.Status != status || p.Type == "" || p.Title == "" {
  return nil, application.ErrInvalidUpstream
 }
 return &application.DependencyFailure{Status: status, Type: p.Type, Title: p.Title, Detail: p.Detail}, nil
}
var _ application.Capture = (*Client)(nil)
