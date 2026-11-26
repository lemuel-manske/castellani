// Package login implements the Capture service client (login perspective).
package login

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

const (
	maxJSONBytes = 1 << 20
)

type Client struct {
	origin url.URL
	http   *http.Client
}

func NewClient(origin url.URL, httpTimeout time.Duration) *Client {
	transport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		ResponseHeaderTimeout: httpTimeout,
		IdleConnTimeout:       90 * time.Second,
		MaxIdleConnsPerHost:   16,
	}

	noRedirect := func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}

	return &Client{
		origin: origin,
		http: &http.Client{
			Timeout:       httpTimeout,
			CheckRedirect: noRedirect,
			Transport:     transport,
		},
	}
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
	request.Header.Set(httpx.HeaderIdempotencyKey, key)

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
