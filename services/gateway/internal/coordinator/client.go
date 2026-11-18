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

	"github.com/lemuel-manske/unnamed/services/gateway/internal/archive"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
)

const (
	maxResponseBytes = 1 << 20
	maxIdleConnections = 32
	maxIdleConnectionsPerHost = 16
	idleConnectionTimeout = 90 * time.Second
)

type Client struct {
	baseURL url.URL
	http    *http.Client
}

type Failure struct {
	Problem httpx.Problem
}

func (f *Failure) Error() string {
	return fmt.Sprintf("coordinator returned HTTP %d", f.Problem.Status)
}

var ErrInvalidResponse = errors.New("invalid coordinator response")

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

func (c *Client) Admit(ctx context.Context, key string, raw []byte) (archive.Accepted, error) {
	request, err := c.request(ctx, http.MethodPost, httpx.ArchivesPath, bytes.NewReader(raw))

	if err != nil {
		return archive.Accepted{}, err
	}
	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	request.Header.Set(httpx.IdempotencyHeader, key)

	status, rawResponse, err := c.execute(request)

	if err != nil {
		return archive.Accepted{}, err
	}

	if status != http.StatusAccepted {
		return archive.Accepted{}, parseFailure(status, rawResponse)
	}

	var accepted archive.Accepted
	decodeErr := json.Unmarshal(rawResponse, &accepted)
	validAdmission := accepted.Status == archive.AcceptedStatus && archive.ValidID(accepted.ArchiveID)

	if decodeErr != nil || !validAdmission {
		return archive.Accepted{}, ErrInvalidResponse
	}
	return accepted, nil
}

func (c *Client) Status(ctx context.Context, id string) (json.RawMessage, error) {
	request, err := c.request(ctx, http.MethodGet, httpx.ArchivePathPrefix+id, nil)

	if err != nil {
		return nil, err
	}
	status, data, err := c.execute(request)

	if err != nil {
		return nil, err
	}

	if status != http.StatusOK {
		return nil, parseFailure(status, data)
	}
	var document struct {
		ArchiveID string          `json:"archiveId"`
		Status    string          `json:"status"`
		Capture   json.RawMessage `json:"capture"`
		Replay    json.RawMessage `json:"replay"`
		Search    json.RawMessage `json:"search"`
	}
	decodeErr := json.Unmarshal(data, &document)
	matchingArchive := document.ArchiveID == id
	completeStatus := document.Status != "" && len(document.Capture) != 0 &&
		len(document.Replay) != 0 && len(document.Search) != 0

	if decodeErr != nil || !matchingArchive || !completeStatus {
		return nil, ErrInvalidResponse
	}
	return json.RawMessage(data), nil
}

func (c *Client) request(ctx context.Context, method, path string, body io.Reader) (*http.Request, error) {
	target := c.baseURL
	target.Path = path
	target.RawPath = ""
	return http.NewRequestWithContext(ctx, method, target.String(), body)
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

func parseFailure(status int, data []byte) error {
	switch status {
	case http.StatusBadRequest, http.StatusConflict, http.StatusUnprocessableEntity,
		http.StatusNotFound, http.StatusServiceUnavailable:
	default:
		return ErrInvalidResponse
	}

	var p httpx.Problem
	decodeErr := json.Unmarshal(data, &p)
	validProblem := p.Status == status && p.Title != "" && p.Type != ""

	if decodeErr != nil || !validProblem {
		return ErrInvalidResponse
	}
	return &Failure{Problem: p}
}
