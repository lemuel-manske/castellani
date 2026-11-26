package testutil

import (
	"io"
	"log/slog"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/services/coordinator/common"
	"github.com/stretchr/testify/require"
)

type Result struct {
	Status int
	Header http.Header
	Body   string
}

func Get(t *testing.T, coordinator, path string) Result {
	return Send(
		t,
		http.MethodGet,
		coordinator,
		path,
		"",
		nil,
	)
}

func Post(
	t *testing.T,
	coordinator, path, body string,
	headers map[string]string,
) Result {
	return Send(
		t,
		http.MethodPost,
		coordinator,
		path,
		body,
		headers,
	)
}

func Send(
	t *testing.T,
	method, coordinator, path, body string,
	headers map[string]string,
) Result {
	t.Helper()

	request, err := http.NewRequest(
		method,
		coordinator+path,
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

func WaitUntilReady(t *testing.T, coordinator string) {
	t.Helper()

	require.Eventually(
		t,
		func() bool {
			response, err := http.Get(coordinator + common.HealthReadyPath)

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
