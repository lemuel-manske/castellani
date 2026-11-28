package tests

import (
	"fmt"
	"net/http"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/fixtures"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/require"
)

// Feature: Archive admission validation
//
// Scenario: Rejecting a submission without an idempotency key
// Given an archive request without an idempotency key
//
// # When the client submits it
//
// Then the request is rejected with an invalid key problem
func TestArchiveSubmission_RejectsMissingIdempotencyKey(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	response := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		fixtures.ValidArchive,
		"Content-Type: application/json",
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)

	require.Equal(
		t,
		ContentTypeProblem,
		response.Header.Get(HeaderContentType),
	)

	require.Equal(
		t,
		fixtures.InvalidIdempotencyKeyProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

// Feature: Archive admission validation
//
// Scenario: Rejecting a submission with a short idempotency key
// Given an archive request with a too-short idempotency key
//
// # When the client submits it
//
// Then the request is rejected with an invalid key problem
func TestArchiveSubmission_RejectsShortIdempotencyKey(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		fixtures.ShortIdempotencyKey,
	)

	response := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		fixtures.ValidArchive,
		headers,
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)

	require.Equal(
		t,
		ContentTypeProblem,
		response.Header.Get(HeaderContentType),
	)

	require.Equal(
		t,
		fixtures.InvalidIdempotencyKeyProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

// Feature: Archive admission validation
//
// Scenario: Rejecting an unsupported content type
// Given an archive request sent as plain text
//
// # When the client submits it
//
// Then the request is rejected with an invalid content type problem
func TestArchiveSubmission_RejectsUnsupportedContentType(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	headers := fmt.Sprintf(
		`Content-Type: text/plain; Idempotency-Key: %s`,
		services.IdempotencyKey("unsupported-content-type"),
	)

	response := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		fixtures.ValidArchive,
		headers,
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)

	require.Equal(
		t,
		ContentTypeProblem,
		response.Header.Get(HeaderContentType),
	)

	require.Equal(
		t,
		fixtures.InvalidContentTypeProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

// Feature: Archive admission validation
//
// Scenario: Rejecting malformed JSON
// Given an archive request with malformed JSON
//
// # When the client submits it
//
// Then the request is rejected with an invalid JSON problem
func TestArchiveSubmission_RejectsMalformedJSON(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("malformed-json"),
	)

	response := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		fixtures.MalformedArchive,
		headers,
	)

	require.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)

	require.Equal(
		t,
		ContentTypeProblem,
		response.Header.Get(HeaderContentType),
	)

	require.Equal(
		t,
		fixtures.InvalidJSONProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}

// Feature: Archive admission validation
//
// Scenario: Rejecting an invalid archive request
// Given an archive request with a negative maximum depth
//
// # When the client submits it
//
// Then the request is rejected with an invalid archive problem
func TestArchiveSubmission_RejectsInvalidRequest(t *testing.T) {
	t.Parallel()

	services := infra.Start(t)

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("invalid-submission"),
	)

	response := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		fixtures.InvalidArchive,
		headers,
	)

	require.Equal(
		t,
		http.StatusUnprocessableEntity,
		response.Status,
	)

	require.Equal(
		t,
		ContentTypeProblem,
		response.Header.Get(HeaderContentType),
	)

	require.Equal(
		t,
		fixtures.InvalidArchiveProblem(),
		testutil.Decode[contracts.Problem](t, response),
	)
}
