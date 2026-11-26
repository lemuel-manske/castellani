package testutil

import (
	"io"
	"log/slog"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/services/gateway/common"
	"github.com/stretchr/testify/require"
)

type Result struct {
	Status int
	Header http.Header
	Body   string
}

func Get(t *testing.T, gateway, path string) Result {
	return Send(
		t,
		http.MethodGet,
		gateway,
		path,
		"",
		nil,
	)
}

func Post(
	t *testing.T,
	gateway, path, body string,
	headers map[string]string,
) Result {
	return Send(
		t,
		http.MethodPost,
		gateway,
		path,
		body,
		headers,
	)
}

func Put(
	t *testing.T,
	gateway, path, body string,
	headers map[string]string,
) Result {
	return Send(
		t,
		http.MethodPut,
		gateway,
		path,
		body,
		headers,
	)
}

func Head(
	t *testing.T,
	gateway, path string,
	headers map[string]string,
) Result {
	return Send(
		t,
		http.MethodHead,
		gateway,
		path,
		"",
		headers,
	)
}

func Send(
	t *testing.T,
	method, gateway, path, body string,
	headers map[string]string,
) Result {
	request, err := http.NewRequest(
		method,
		gateway+path,
		strings.NewReader(body),
	)
	require.NoError(t, err)

	for name, value := range headers {
		request.Header.Set(name, value)
	}

	response, err := http.DefaultClient.Do(request)
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

func WaitUntilReady(t *testing.T, gateway string) {
	require.Eventually(
		t,
		func() bool {
			response, err := http.Get(gateway + common.HealthReadyPath)

			if err != nil {
				return false
			}

			defer response.Body.Close()

			return response.StatusCode == http.StatusOK
		},
		5*time.Second,
		10*time.Millisecond,
	)
}

func Logger() *slog.Logger {
	return slog.New(
		slog.NewTextHandler(
			io.Discard,
			nil,
		),
	)
}
