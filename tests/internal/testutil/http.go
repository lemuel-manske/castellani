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

var client = &http.Client{
	Timeout: 10 * time.Second,
}

type Result struct {
	Status int
	Header http.Header
	Body   string
}

func Get(t *testing.T, url string) Result {
	t.Helper()

	emptyBody := ""
	noHeaders := ""

	return Send(
		t,
		http.MethodGet,
		url,
		emptyBody,
		noHeaders,
	)
}

func GetWithHeaders(t *testing.T, url string, headers string) Result {
	t.Helper()

	emptyBody := ""

	return Send(
		t,
		http.MethodGet,
		url,
		emptyBody,
		headers,
	)
}

func Post(
	t *testing.T,
	url string,
	body string,
	headers string,
) Result {
	t.Helper()

	return Send(
		t,
		http.MethodPost,
		url,
		body,
		headers,
	)
}

func Head(t *testing.T, url string) Result {
	t.Helper()

	emptyBody := ""
	noHeaders := ""

	return Send(
		t,
		http.MethodHead,
		url,
		emptyBody,
		noHeaders,
	)
}

func Send(
	t *testing.T,
	method string,
	url string,
	body string,
	headers string,
) Result {
	t.Helper()

	request, err := http.NewRequest(
		method,
		url,
		strings.NewReader(body),
	)

	require.NoError(t, err)

	headersMap := asMap(headers)

	for name, value := range headersMap {
		request.Header.Set(name, value)
	}

	response, err := client.Do(request)
	require.NoError(t, err)

	defer response.Body.Close()

	data, err := io.ReadAll(response.Body)
	require.NoError(t, err)

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

func asMap(headers string) map[string]string {
	result := make(map[string]string)

	for line := range strings.SplitSeq(headers, ";") {
		line = strings.TrimSpace(line)

		if line == "" {
			continue
		}

		parts := strings.SplitN(line, ":", 2)

		if len(parts) != 2 {
			continue
		}

		name := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])

		result[name] = value
	}

	return result
}
