package tests_test

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/stretchr/testify/require"
)

type problemDetails struct {
	Type     string `json:"type"`
	Title    string `json:"title"`
	Status   int    `json:"status"`
	Detail   string `json:"detail"`
	Instance string `json:"instance"`
}

func TestGateway_CreateArchiveRejectsMissingIdempotencyKey(t *testing.T) {
	services := infra.Start(t)

	request, err := http.NewRequest(
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

	var problem problemDetails
	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))
	require.Equal(t, problemDetails{
		Type:     "urn:distributed-web-archive:problem:idempotency-key",
		Title:    "Invalid Idempotency Key",
		Status:   http.StatusBadRequest,
		Instance: "/archives",
	}, problemDetails{
		Type:     problem.Type,
		Title:    problem.Title,
		Status:   problem.Status,
		Instance: problem.Instance,
	})
	require.NotEmpty(t, problem.Detail)
}

func TestGateway_CreateArchiveRejectsShortIdempotencyKey(t *testing.T) {
	services := infra.Start(t)

	request, err := http.NewRequest(
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

	var problem problemDetails
	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))
	require.Equal(t, problemDetails{
		Type:     "urn:distributed-web-archive:problem:idempotency-key",
		Title:    "Invalid Idempotency Key",
		Status:   http.StatusBadRequest,
		Instance: "/archives",
	}, problemDetails{
		Type:     problem.Type,
		Title:    problem.Title,
		Status:   problem.Status,
		Instance: problem.Instance,
	})
	require.NotEmpty(t, problem.Detail)
}
