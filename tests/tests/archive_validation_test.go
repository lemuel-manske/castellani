package tests

import (
	"net/http"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/fixtures"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestArchiveSubmission_RejectsMissingIdempotencyKey(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		fixtures.ValidArchive,
		map[string]string{
			testutil.HeaderContentType: testutil.ContentTypeJSON,
		},
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)
	assert.Equal(
		t,
		testutil.ContentTypeProblem,
		response.Header.Get(testutil.HeaderContentType),
	)
	assert.Equal(
		t,
		fixtures.InvalidIdempotencyKeyProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

func TestArchiveSubmission_RejectsShortIdempotencyKey(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		fixtures.ValidArchive,
		map[string]string{
			testutil.HeaderContentType:    testutil.ContentTypeJSON,
			testutil.HeaderIdempotencyKey: fixtures.ShortIdempotencyKey,
		},
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)
	assert.Equal(
		t,
		testutil.ContentTypeProblem,
		response.Header.Get(testutil.HeaderContentType),
	)
	assert.Equal(
		t,
		fixtures.InvalidIdempotencyKeyProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

func TestArchiveSubmission_RejectsUnsupportedContentType(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		fixtures.ValidArchive,
		map[string]string{
			testutil.HeaderContentType:    "text/plain",
			testutil.HeaderIdempotencyKey: services.IdempotencyKey("unsupported-content-type"),
		},
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)
	assert.Equal(
		t,
		testutil.ContentTypeProblem,
		response.Header.Get(testutil.HeaderContentType),
	)
	assert.Equal(
		t,
		fixtures.InvalidContentTypeProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

func TestArchiveSubmission_RejectsMalformedJSON(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		fixtures.MalformedArchive,
		map[string]string{
			testutil.HeaderContentType:    testutil.ContentTypeJSON,
			testutil.HeaderIdempotencyKey: services.IdempotencyKey("malformed-json"),
		},
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)
	assert.Equal(
		t,
		testutil.ContentTypeProblem,
		response.Header.Get(testutil.HeaderContentType),
	)
	assert.Equal(
		t,
		fixtures.InvalidJSONProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

func TestArchiveSubmission_RejectsInvalidRequest(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		fixtures.InvalidArchive,
		map[string]string{
			testutil.HeaderContentType:    testutil.ContentTypeJSON,
			testutil.HeaderIdempotencyKey: services.IdempotencyKey("invalid-submission"),
		},
	)

	require.Equal(
		t,
		http.StatusUnprocessableEntity,
		response.Status,
	)
	assert.Equal(
		t,
		testutil.ContentTypeProblem,
		response.Header.Get(testutil.HeaderContentType),
	)
	assert.Equal(
		t,
		fixtures.InvalidArchiveProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}
