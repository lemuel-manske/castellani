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

func NewClient(origin url.URL, httpTimeout, streamTimeout time.Duration) *Client {
	transport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		ResponseHeaderTimeout: httpTimeout,
		IdleConnTimeout:       90 * time.Second,
		MaxIdleConnsPerHost:   16,
	}

	noRedirect := func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}

	if streamTimeout <= 0 {
		streamTimeout = defaultStreamTimeout
	}

	return &Client{
		origin: origin,
		http: &http.Client{
			Timeout:       httpTimeout,
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

	target := c.origin

	target.Path = common.ArchivePathPrefix + url.PathEscape(archiveID) + common.PagesPathSuffix
	target.RawQuery = query.Encode()

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		target.String(),
		nil,
	)

	if err != nil {
		return Pages{}, err
	}

	data, err := c.execute(request, http.StatusOK)

	if err != nil {
		return Pages{}, err
	}

	var result Pages

	if err := json.Unmarshal(data, &result); err != nil {
		return Pages{}, ErrInvalidResponse
	}

	return result, nil
}

func (c *Client) GetSnapshot(ctx context.Context, archiveID, snapshotID string) (Snapshot, error) {
	target := c.origin
	target.Path = common.ArchivePathPrefix +
		url.PathEscape(archiveID) +
		common.SnapshotPathSegment +
		url.PathEscape(snapshotID)

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		target.String(),
		nil,
	)

	if err != nil {
		return Snapshot{}, err
	}

	data, err := c.execute(request, http.StatusOK)

	if err != nil {
		return Snapshot{}, err
	}

	var result Snapshot

	if err := json.Unmarshal(data, &result); err != nil {
		return Snapshot{}, ErrInvalidResponse
	}

	return result, nil
}

func (c *Client) CreateSession(
	ctx context.Context,
	key string,
	session SessionRequest,
	raw []byte,
) (Session, error) {
	target := c.origin
	target.Path = common.SessionsPath

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		target.String(),
		bytes.NewReader(raw),
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

	var result Session

	if err := json.Unmarshal(data, &result); err != nil {
		return Session{}, ErrInvalidResponse
	}

	return result, nil
}

func (c *Client) GetSession(ctx context.Context, id string) (Session, error) {
	target := c.origin
	target.Path = common.SessionPathPrefix + url.PathEscape(id)

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		target.String(),
		nil,
	)

	if err != nil {
		return Session{}, err
	}

	data, err := c.execute(request, http.StatusOK)

	if err != nil {
		return Session{}, err
	}

	var result Session

	if err := json.Unmarshal(data, &result); err != nil {
		return Session{}, ErrInvalidResponse
	}

	return result, nil
}

func (c *Client) UpdateSession(
	ctx context.Context,
	id string,
	raw []byte,
) (Session, error) {
	target := c.origin
	target.Path = common.SessionPathPrefix + url.PathEscape(id)

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPut,
		target.String(),
		bytes.NewReader(raw),
	)

	if err != nil {
		return Session{}, err
	}

	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)

	data, err := c.execute(request, http.StatusOK)

	if err != nil {
		return Session{}, err
	}

	var result Session

	if err := json.Unmarshal(data, &result); err != nil {
		return Session{}, ErrInvalidResponse
	}

	return result, nil
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

	target := c.origin
	target.Path = common.ArchivePathPrefix + url.PathEscape(id) + common.WACZPathSuffix

	request, err := http.NewRequestWithContext(
		ctx,
		method,
		target.String(),
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

	if response.StatusCode >= http.StatusBadRequest {
		defer response.Body.Close()

		data, readErr := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))

		if readErr != nil || len(data) > maxJSONBytes {
			return WACZ{}, ErrInvalidResponse
		}

		var problem httpx.Problem

		if err := json.Unmarshal(data, &problem); err != nil {
			return WACZ{}, ErrInvalidResponse
		}

		return WACZ{}, &Failure{
			Status: response.StatusCode,
			Type:   problem.Type,
			Title:  problem.Title,
			Detail: problem.Detail,
		}
	}

	success := response.StatusCode == http.StatusOK ||
		response.StatusCode == http.StatusPartialContent

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
		if response.StatusCode < http.StatusBadRequest {
			return nil, ErrInvalidResponse
		}

		var problem httpx.Problem

		if err := json.Unmarshal(data, &problem); err != nil {
			return nil, ErrInvalidResponse
		}

		return nil, &Failure{
			Status: problem.Status,
			Type:   problem.Type,
			Title:  problem.Title,
			Detail: problem.Detail,
		}
	}

	if !json.Valid(data) || bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
		return nil, ErrInvalidResponse
	}

	return data, nil
}
