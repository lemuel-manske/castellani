package tests

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/stretchr/testify/require"
)

func TestGateway_CreateArchiveRejectsUnsupportedContentType(t *testing.T) {
	services := infra.Start(t)

	request, err := http.NewRequest(
		http.MethodPost,
		services.Gateway.URL("/archives"),
		strings.NewReader(`{"seedUrl":"https://example.com","maxDepth":1,"maxPages":10}`),
	)
	require.NoError(t, err)

	request.Header.Set("Idempotency-Key", "archive-test-0002")
	request.Header.Set("Content-Type", "text/plain")

	response, err := http.DefaultClient.Do(request)
	require.NoError(t, err)

	defer response.Body.Close()

	require.Equal(t, http.StatusBadRequest, response.StatusCode)

	require.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))

	var problem Problem

	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))

	require.Equal(t, Problem{
		Type:     "urn:distributed-web-archive:problem:content-type",
		Title:    "Invalid Content Type",
		Status:   http.StatusBadRequest,
		Detail:   "Expected application/json.",
		Instance: "/archives",
	}, problem)
}

func TestGateway_CreateArchiveRejectsMalformedJSON(t *testing.T) {
	services := infra.Start(t)

	request, err := http.NewRequest(
		http.MethodPost,
		services.Gateway.URL("/archives"),
		strings.NewReader(`{"seedUrl":`),
	)
	require.NoError(t, err)

	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "archive-test-0003")

	response, err := http.DefaultClient.Do(request)
	require.NoError(t, err)

	defer response.Body.Close()

	require.Equal(t, http.StatusBadRequest, response.StatusCode)

	require.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))

	var problem Problem

	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))

	require.Equal(t, Problem{
		Type:     "urn:distributed-web-archive:problem:invalid-json",
		Title:    "Invalid Request",
		Status:   http.StatusBadRequest,
		Detail:   "Expected a valid archive JSON object.",
		Instance: "/archives",
	}, problem)
}

func TestGateway_CreateArchiveRejectsInvalidSubmission(t *testing.T) {
	services := infra.Start(t)

	request, err := http.NewRequest(
		http.MethodPost,
		services.Gateway.URL("/archives"),
		strings.NewReader(`{
			"seedUrl": "https://example.com",
			"maxDepth": -1,
			"maxPages": 10
		}`),
	)
	require.NoError(t, err)

	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "archive-test-0004")

	response, err := http.DefaultClient.Do(request)
	require.NoError(t, err)

	defer response.Body.Close()

	require.Equal(t, http.StatusUnprocessableEntity, response.StatusCode)

	require.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))

	var problem Problem

	require.NoError(t, json.NewDecoder(response.Body).Decode(&problem))

	require.Equal(t, Problem{
		Type:     "urn:distributed-web-archive:problem:invalid-archive",
		Title:    "Invalid Archive",
		Status:   http.StatusUnprocessableEntity,
		Detail:   "invalid submission: maxDepth must be a nonnegative integer",
		Instance: "/archives",
	}, problem)
}
