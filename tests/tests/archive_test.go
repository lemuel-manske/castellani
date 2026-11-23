package tests_test

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/stretchr/testify/require"
)

func TestGateway_CreateArchiveRejectsMissingIdempotencyKey(t *testing.T) {
	services := infra.Start(t)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		services.Gateway.URL("/archives"),
		strings.NewReader("{}"),
	)
	require.NoError(t, err)

	request.Header.Set("Content-Type", "application/json")

	response, err := http.DefaultClient.Do(request)
	require.NoError(t, err)
	defer response.Body.Close()

	require.Equal(t, http.StatusBadRequest, response.StatusCode)
	require.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))

	var problem struct {
		Type     string `json:"type"`
		Title    string `json:"title"`
		Status   int    `json:"status"`
		Detail   string `json:"detail"`
		Instance string `json:"instance"`
	}

	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))
	require.Equal(t, "urn:distributed-web-archive:problem:idempotency-key", problem.Type)
	require.Equal(t, "Invalid Idempotency Key", problem.Title)
	require.Equal(t, http.StatusBadRequest, problem.Status)
	require.Equal(t, "/archives", problem.Instance)
	require.NotEmpty(t, problem.Detail)
}

func TestGateway_CreateArchiveRejectsShortIdempotencyKey(t *testing.T) {
	services := infra.Start(t)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		services.Gateway.URL("/archives"),
		strings.NewReader("{}"),
	)
	require.NoError(t, err)

	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "short")

	response, err := http.DefaultClient.Do(request)
	require.NoError(t, err)
	defer response.Body.Close()

	require.Equal(t, http.StatusBadRequest, response.StatusCode)
	require.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))

	var problem struct {
		Type     string `json:"type"`
		Title    string `json:"title"`
		Status   int    `json:"status"`
		Detail   string `json:"detail"`
		Instance string `json:"instance"`
	}

	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))
	require.Equal(t, "urn:distributed-web-archive:problem:idempotency-key", problem.Type)
	require.Equal(t, "Invalid Idempotency Key", problem.Title)
	require.Equal(t, http.StatusBadRequest, problem.Status)
	require.Equal(t, "/archives", problem.Instance)
	require.NotEmpty(t, problem.Detail)
}
