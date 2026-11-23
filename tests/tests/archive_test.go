package tests_test

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/stretchr/testify/require"
)

type Problem struct {
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

	var problem Problem

	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))

	require.NotEmpty(t, problem.Detail)

	require.Equal(t, Problem{
		Type:     "urn:distributed-web-archive:problem:idempotency-key",
		Title:    "Invalid Idempotency Key",
		Status:   http.StatusBadRequest,
		Detail:   problem.Detail,
		Instance: "/archives",
	}, problem)
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

	var problem Problem

	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))

	require.NotEmpty(t, problem.Detail)

	require.Equal(t, Problem{
		Type:     "urn:distributed-web-archive:problem:idempotency-key",
		Title:    "Invalid Idempotency Key",
		Status:   http.StatusBadRequest,
		Detail:   problem.Detail,
		Instance: "/archives",
	}, problem)
}
