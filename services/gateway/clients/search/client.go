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
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

const maxJSONBytes = 1 << 20

type Client struct {
	origin url.URL
	http   *http.Client
}

func NewClient(origin url.URL, timeout time.Duration) *Client {
	return &Client{
		origin: origin,
		http: &http.Client{
			Timeout:       timeout,
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
			Transport: &http.Transport{
				Proxy:                 http.ProxyFromEnvironment,
				ResponseHeaderTimeout: timeout,
				IdleConnTimeout:       90 * time.Second,
				MaxIdleConnsPerHost:   16,
			},
		},
	}
}

func (c *Client) Search(ctx context.Context, query Query) (Results, error) {
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
	target.RawQuery = values.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)

	if err != nil {
		return Results{}, err
	}

	response, err := c.http.Do(request)

	if err != nil {
		return Results{}, fmt.Errorf("%w: search request: %v", ErrUnavailable, err)
	}

	defer response.Body.Close()

	data, err := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))

	if err != nil {
		return Results{}, fmt.Errorf("%w: read search: %v", ErrUnavailable, err)
	}

	if len(data) > maxJSONBytes {
		return Results{}, ErrInvalidResponse
	}

	if response.StatusCode != http.StatusOK {
		if response.StatusCode < http.StatusBadRequest {
			return Results{}, ErrInvalidResponse
		}

		var problem httpx.Problem

		if json.Unmarshal(data, &problem) != nil ||
			problem.Status != response.StatusCode ||
			problem.Type == "" ||
			problem.Title == "" {
			return Results{}, ErrInvalidResponse
		}

		return Results{}, &Failure{
			Status: response.StatusCode,
			Type:   problem.Type,
			Title:  problem.Title,
			Detail: problem.Detail,
		}
	}

	var result Results

	if err = json.Unmarshal(data, &result); err != nil {
		return Results{}, ErrInvalidResponse
	}

	return result, nil
}
