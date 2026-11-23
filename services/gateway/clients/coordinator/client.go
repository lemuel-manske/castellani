// Package coordinator provides a client for communicating with the coordinator service
package coordinator

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

const (
	maxResponseBytes          = 1 << 20
	maxIdleConnections        = 32
	maxIdleConnectionsPerHost = 16
	idleConnectionTimeout     = 90 * time.Second
)

var ErrInvalidResponse = errors.New("invalid coordinator response")

type Client struct {
	baseURL url.URL
	http    *http.Client
}

func NewClient(origin url.URL, timeout time.Duration) *Client {
	return &Client{
		baseURL: origin,
		http: &http.Client{
			Timeout: timeout,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
			Transport: &http.Transport{
				Proxy:                 http.ProxyFromEnvironment,
				MaxIdleConns:          maxIdleConnections,
				MaxIdleConnsPerHost:   maxIdleConnectionsPerHost,
				IdleConnTimeout:       idleConnectionTimeout,
				ResponseHeaderTimeout: timeout,
			},
		},
	}
}

func (c *Client) CreateArchive(
	ctx context.Context,
	key string,
	raw []byte,
) (Accepted, error) {
	target := c.baseURL
	target.Path = common.ArchivesPath

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		target.String(),
		bytes.NewReader(raw),
	)

	if err != nil {
		return Accepted{}, err
	}

	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	request.Header.Set(httpx.IdempotencyHeader, key)

	status, rawResponse, err := c.execute(request)

	if err != nil {
		return Accepted{}, err
	}

	if status != http.StatusAccepted {
		var problem httpx.Problem

		if err := json.Unmarshal(rawResponse, &problem); err != nil {
			return Accepted{}, ErrInvalidResponse
		}

		return Accepted{}, &Failure{
			Status: problem.Status,
			Type:   problem.Type,
			Title:  problem.Title,
			Detail: problem.Detail,
		}
	}

	var accepted Accepted

	if json.Unmarshal(rawResponse, &accepted) != nil {
		return Accepted{}, ErrInvalidResponse
	}

	return accepted, nil
}

func (c *Client) GetArchive(ctx context.Context, id string) (json.RawMessage, error) {
	target := c.baseURL
	target.Path = common.ArchivePathPrefix + id

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		target.String(),
		nil,
	)

	if err != nil {
		return nil, err
	}

	status, data, err := c.execute(request)

	if err != nil {
		return nil, err
	}

	if status != http.StatusOK {
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

	return json.RawMessage(data), nil
}

func (c *Client) execute(request *http.Request) (int, []byte, error) {
	response, err := c.http.Do(request)

	if err != nil {
		return 0, nil, fmt.Errorf("coordinator HTTP call: %w", err)
	}

	defer response.Body.Close()

	data, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))

	if err != nil {
		return 0, nil, fmt.Errorf("read coordinator response: %w", err)
	}

	if len(data) > maxResponseBytes {
		return 0, nil, ErrInvalidResponse
	}

	return response.StatusCode, data, nil
}
