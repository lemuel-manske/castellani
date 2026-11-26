// Package testutil provides HTTP helpers for the end-to-end test suite.
package testutil

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

const (
	ContentTypeJSON    = "application/json"
	ContentTypeProblem = "application/problem+json"

	HeaderContentType    = "Content-Type"
	HeaderIdempotencyKey = "Idempotency-Key"
	HeaderLocation       = "Location"
)

var client = &http.Client{
	Timeout: 10 * time.Second,
}

type Result struct {
	Status int
	Header http.Header
	Body   string
}

func Get(t *testing.T, baseURL, path string) Result {
	t.Helper()

	return Send(
		t,
		http.MethodGet,
		baseURL,
		path,
		"",
		nil,
	)
}

func Post(
	t *testing.T,
	baseURL, path, body string,
	headers map[string]string,
) Result {
	t.Helper()

	return Send(
		t,
		http.MethodPost,
		baseURL,
		path,
		body,
		headers,
	)
}

func Send(
	t *testing.T,
	method, baseURL, path, body string,
	headers map[string]string,
) Result {
	t.Helper()

	request, err := http.NewRequest(
		method,
		baseURL+path,
		strings.NewReader(body),
	)
	require.NoError(t, err)

	for name, value := range headers {
		request.Header.Set(name, value)
	}

	response, err := client.Do(request)
	require.NoError(t, err)

	defer response.Body.Close()

	data, err := io.ReadAll(response.Body)
	require.NoErrorf(
		t,
		err,
		"reading %s %s: status=%s content-length=%q content-range=%q content-type=%q transfer-encoding=%q bytes-read=%d",
		method,
		request.URL,
		response.Status,
		response.Header.Get("Content-Length"),
		response.Header.Get("Content-Range"),
		response.Header.Get("Content-Type"),
		response.Header.Get("Transfer-Encoding"),
		len(data),
	)

	return Result{
		Status: response.StatusCode,
		Header: response.Header.Clone(),
		Body:   string(data),
	}
}

func Decode[T any](t *testing.T, result Result) T {
	t.Helper()

	var value T

	require.NoError(t, json.Unmarshal([]byte(result.Body), &value))

	return value
}
