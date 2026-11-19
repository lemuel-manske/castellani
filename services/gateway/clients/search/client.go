// Package search implements the Search service client.
package search

import (
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

const maxJSONBytes = 1 << 20

var _ application.SearchService = (*Client)(nil)

type Client struct {
	origin url.URL
	http   *http.Client
}

func NewClient(origin url.URL, timeout time.Duration) *Client {
	return &Client{origin: origin, http: &http.Client{
		Timeout:       timeout,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		Transport:     &http.Transport{Proxy: http.ProxyFromEnvironment, ResponseHeaderTimeout: timeout, IdleConnTimeout: 90 * time.Second, MaxIdleConnsPerHost: 16},
	}}
}

func (c *Client) Search(ctx context.Context, query application.SearchQuery) (json.RawMessage, error) {
	values := url.Values{}
	values.Set("q", query.Text)

	if query.CollectionID != "" {
		values.Set("collectionId", query.CollectionID)
	}

	if query.ArchiveID != "" {
		values.Set("archiveId", query.ArchiveID)
	}

	if query.SnapshotID != "" {
		values.Set("snapshotId", query.SnapshotID)
	}

	if query.CapturedFrom != "" {
		values.Set("capturedFrom", query.CapturedFrom)
	}

	if query.CapturedTo != "" {
		values.Set("capturedTo", query.CapturedTo)
	}

	if query.Pagination.Limit != nil {
		values.Set("limit", strconv.Itoa(*query.Pagination.Limit))
	}

	if query.Pagination.Cursor != "" {
		values.Set("cursor", query.Pagination.Cursor)
	}
	target := c.origin
	target.Path = common.SearchPath
	target.RawPath = ""
	target.RawQuery = values.Encode()
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		target.String(),
		nil,
	)

	if err != nil {
		return nil, err
	}
	response, err := c.http.Do(request)

	if err != nil {
		return nil, fmt.Errorf(
			"%w: search request: %v",
			application.ErrDependencyUnavailable,
			err,
		)
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))

	if err != nil {
		return nil, fmt.Errorf(
			"%w: read search: %v",
			application.ErrDependencyUnavailable,
			err,
		)
	}

	if len(data) > maxJSONBytes {
		return nil, application.ErrInvalidUpstream
	}

	if response.StatusCode != http.StatusOK {
		switch response.StatusCode {
		case 400, 401, 403, 404, 409, 422, 503:
		default:
			return nil, application.ErrInvalidUpstream
		}
		var p httpx.Problem

		if json.Unmarshal(data, &p) != nil || p.Status != response.StatusCode || p.Title == "" || p.Type == "" {
			return nil, application.ErrInvalidUpstream
		}
		return nil, &application.DependencyFailure{Status: p.Status, Type: p.Type, Title: p.Title, Detail: p.Detail}
	}
	var result struct {
		Results []json.RawMessage `json:"results"`
	}

	if json.Unmarshal(data, &result) != nil || result.Results == nil {
		return nil, application.ErrInvalidUpstream
	}
	return data, nil
}
