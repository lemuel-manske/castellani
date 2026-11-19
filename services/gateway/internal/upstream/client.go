package upstream

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
)

const (
	maxJSONBytes         = 1 << 20
	idleTimeout          = 90 * time.Second
	defaultStreamTimeout = 30 * time.Minute
)

var ErrInvalidResponse = errors.New("invalid upstream response")

type Result struct {
	Status int
	Body   []byte
}

type Client struct {
	baseURL url.URL
	http    *http.Client
	stream  *http.Client
}

func NewClient(origin url.URL, timeout time.Duration) *Client {
	return NewClientWithStreamTimeout(origin, timeout, defaultStreamTimeout)
}

func NewClientWithStreamTimeout(origin url.URL, timeout, streamTimeout time.Duration) *Client {
	transport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		ResponseHeaderTimeout: timeout,
		IdleConnTimeout:       idleTimeout,
		MaxIdleConnsPerHost:   16,
	}

	noRedirect := func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}

	return &Client{
		baseURL: origin,
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

func (c *Client) JSON(ctx context.Context, method, path, query, key string, body []byte) (Result, error) {
	request, err := c.request(ctx, method, path, query, bytes.NewReader(body))

	if err != nil {
		return Result{}, err
	}

	if body != nil {
		request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	}

	if key != "" {
		request.Header.Set(httpx.IdempotencyHeader, key)
	}

	response, err := c.http.Do(request)

	if err != nil {
		return Result{}, fmt.Errorf("upstream HTTP call: %w", err)
	}

	defer response.Body.Close()

	data, err := io.ReadAll(io.LimitReader(response.Body, maxJSONBytes+1))

	if err != nil {
		return Result{}, fmt.Errorf("read upstream HTTP response: %w", err)
	}

	if len(data) > maxJSONBytes {
		return Result{}, ErrInvalidResponse
	}

	return Result{Status: response.StatusCode, Body: data}, nil
}

// Stream uses a separate bounded transfer deadline and caller cancellation.
// The caller must close the response body.
func (c *Client) Stream(ctx context.Context, method, path, byteRange, ifRange string) (*http.Response, error) {
	request, err := c.request(ctx, method, path, "", nil)

	if err != nil {
		return nil, err
	}

	if byteRange != "" {
		request.Header.Set("Range", byteRange)
	}

	if ifRange != "" {
		request.Header.Set("If-Range", ifRange)
	}

	response, err := c.stream.Do(request)

	if err != nil {
		return nil, fmt.Errorf("stream from upstream: %w", err)
	}

	return response, nil
}

func (c *Client) request(ctx context.Context, method, path, query string, body io.Reader) (*http.Request, error) {
	target := c.baseURL
	target.Path = path
	target.RawPath = ""
	target.RawQuery = query

	return http.NewRequestWithContext(ctx, method, target.String(), body)
}
