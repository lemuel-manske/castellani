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
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

const (
	maxJSONBytes         = 1 << 20
	defaultStreamTimeout = 30 * time.Minute
)

type Client struct {
	origin       url.URL
	http, stream *http.Client
}

func NewClient(origin url.URL, timeout, streamTimeout time.Duration) *Client {
	transport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		ResponseHeaderTimeout: timeout,
		IdleConnTimeout:       90 * time.Second,
		MaxIdleConnsPerHost:   16,
	}
	noRedirect := func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }

	if streamTimeout <= 0 {
		streamTimeout = defaultStreamTimeout
	}

	return &Client{
		origin: origin,
		http: &http.Client{
			Timeout:       timeout,
			CheckRedirect: noRedirect,
			Transport:     transport,
		},
		stream: &http.Client{
			Timeout:       streamTimeout,
			CheckRedirect: noRedirect,
			Transport:     transport,
		},
	}
}

func (c *Client) ListPages(
	ctx context.Context,
	archiveID string,
	page Pagination,
) (Pages, error) {
	query := url.Values{}

	if page.Limit != nil {
		query.Set("limit", strconv.Itoa(*page.Limit))
	}

	if page.Cursor != "" {
		query.Set("cursor", page.Cursor)
	}
	path := common.ArchivePathPrefix + url.PathEscape(archiveID) + common.PagesPathSuffix
	request, err := c.request(
		ctx,
		http.MethodGet,
		path,
		query.Encode(),
		nil,
	)

	if err != nil {
		return Pages{}, err
	}
	data, err := c.execute(request, http.StatusOK)

	if err != nil {
		return Pages{}, err
	}
	var v Pages

	if json.Unmarshal(data, &v) != nil || v.Items == nil {
		return Pages{}, ErrInvalidResponse
	}

	return v, nil
}

func (c *Client) GetSnapshot(ctx context.Context, archiveID, snapshotID string) (Snapshot, error) {
	path := common.ArchivePathPrefix + url.PathEscape(archiveID) + common.SnapshotPathSegment + url.PathEscape(snapshotID)
	request, err := c.request(
		ctx,
		http.MethodGet,
		path,
		"",
		nil,
	)

	if err != nil {
		return Snapshot{}, err
	}
	data, err := c.execute(request, http.StatusOK)

	if err != nil {
		return Snapshot{}, err
	}
	var v Snapshot

	if json.Unmarshal(data, &v) != nil || v.ArchiveID != archiveID || v.SnapshotID != snapshotID || v.URL == "" || v.CapturedAt == "" {
		return Snapshot{}, ErrInvalidResponse
	}

	return v, nil
}

func (c *Client) CreateSession(
	ctx context.Context,
	key string,
	session SessionRequest,
	raw []byte,
) (Session, error) {
	request, err := c.request(
		ctx,
		http.MethodPost,
		common.SessionsPath,
		"",
		raw,
	)

	if err != nil {
		return Session{}, err
	}
	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	request.Header.Set(httpx.IdempotencyHeader, key)

	data, err := c.execute(request, http.StatusCreated)

	if err != nil {
		return Session{}, err
	}

	return validateSession(
		data,
		"",
		session.ArchiveID,
	)
}

func (c *Client) GetSession(ctx context.Context, id string) (Session, error) {
	return c.session(
		ctx,
		http.MethodGet,
		id,
		nil,
	)
}

func (c *Client) UpdateSession(
	ctx context.Context,
	id string,
	raw []byte,
) (Session, error) {
	return c.session(
		ctx,
		http.MethodPut,
		id,
		raw,
	)
}

func (c *Client) session(
	ctx context.Context,
	method, id string,
	raw []byte,
) (Session, error) {
	request, err := c.request(
		ctx,
		method,
		common.SessionPathPrefix+url.PathEscape(id),
		"",
		raw,
	)

	if err != nil {
		return Session{}, err
	}

	if raw != nil {
		request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	}

	data, err := c.execute(request, http.StatusOK)

	if err != nil {
		return Session{}, err
	}

	return validateSession(
		data,
		id,
		"",
	)
}

func validateSession(data []byte, id, archiveID string) (Session, error) {
	var v Session

	isValid := (json.Unmarshal(data, &v) == nil &&
		httpx.ValidPathSegment(v.SessionID) &&
		httpx.ValidPathSegment(v.ArchiveID) &&
		v.Status != "" &&
		v.ExpiresAt != "" &&
		(id == "" || v.SessionID == id) &&
		(archiveID == "" || v.ArchiveID == archiveID))

	if !isValid {
		return Session{}, ErrInvalidResponse
	}

	return v, nil
}

func (c *Client) GetWACZ(
	ctx context.Context,
	id string,
	options WACZOptions,
) (WACZ, error) {
	method := http.MethodGet

	if options.MetadataOnly {
		method = http.MethodHead
	}

	path := common.ArchivePathPrefix + url.PathEscape(id) + common.WACZPathSuffix

	request, err := c.request(
		ctx,
		method,
		path,
		"",
		nil,
	)

	if err != nil {
		return WACZ{}, err
	}

	if options.Range != "" {
		request.Header.Set("Range", options.Range)
	}

	if options.IfRange != "" {
		request.Header.Set("If-Range", options.IfRange)
	}

	response, err := c.stream.Do(request)

	if err != nil {
		return WACZ{}, fmt.Errorf(
			"%w: capture WACZ: %v",
			ErrUnavailable,
			err,
		)
	}

	if response.StatusCode == http.StatusNotFound || response.StatusCode == http.StatusServiceUnavailable || response.StatusCode == http.StatusRequestedRangeNotSatisfiable {
		defer response.Body.Close()

		data, err := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))

		if err != nil || len(data) > maxJSONBytes {
			return WACZ{}, ErrInvalidResponse
		}

		failure, err := parseFailure(response.StatusCode, data)

		if err != nil {
			return WACZ{}, err
		}

		failure.ContentRange = response.Header.Get("Content-Range")

		return WACZ{}, failure
	}

	success := response.StatusCode == http.StatusOK || response.StatusCode == http.StatusPartialContent

	if !success || response.Header.Get(httpx.HeaderContentType) != httpx.WACZMediaType {
		response.Body.Close()

		return WACZ{}, ErrInvalidResponse
	}

	return WACZ{
		Body:          response.Body,
		Partial:       response.StatusCode == http.StatusPartialContent,
		AcceptRanges:  response.Header.Get("Accept-Ranges"),
		ContentRange:  response.Header.Get("Content-Range"),
		ETag:          response.Header.Get("ETag"),
		LastModified:  response.Header.Get("Last-Modified"),
		ContentLength: response.Header.Get("Content-Length"),
	}, nil
}

func (c *Client) execute(request *http.Request, success int) (json.RawMessage, error) {
	response, err := c.http.Do(request)

	if err != nil {
		return nil, fmt.Errorf(
			"%w: capture request: %v",
			ErrUnavailable,
			err,
		)
	}
	defer response.Body.Close()

	data, err := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))

	if err != nil {
		return nil, fmt.Errorf(
			"%w: read capture: %v",
			ErrUnavailable,
			err,
		)
	}

	if len(data) > maxJSONBytes {
		return nil, ErrInvalidResponse
	}

	if response.StatusCode != success {
		// Range failures are part of the WACZ protocol, not JSON endpoints.
		if response.StatusCode == http.StatusRequestedRangeNotSatisfiable {
			return nil, ErrInvalidResponse
		}

		failure, err := parseFailure(response.StatusCode, data)

		if err != nil {
			return nil, err
		}

		return nil, failure
	}

if !json.Valid(data) || bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
		return nil, ErrInvalidResponse
	}

	return data, nil
}

func (c *Client) request(
	ctx context.Context,
	method, path, query string,
	body []byte,
) (*http.Request, error) {
	target := c.origin

	target.Path = path
	target.RawPath = ""
	target.RawQuery = query

	return http.NewRequestWithContext(
		ctx,
		method,
		target.String(),
		bytes.NewReader(body),
	)
}

func parseFailure(status int, data []byte) (*Failure, error) {
	switch status {
	case 400, 401, 403, 404, 409, 416, 422, 503:
	default:
		return nil, ErrInvalidResponse
	}
	var p httpx.Problem

	if json.Unmarshal(data, &p) != nil || p.Status != status || p.Type == "" || p.Title == "" {
		return nil, ErrInvalidResponse
	}

	return &Failure{
		Status: status,
		Type:   p.Type,
		Title:  p.Title,
		Detail: p.Detail,
	}, nil
}
