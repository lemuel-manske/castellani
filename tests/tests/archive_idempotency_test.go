package tests

import (
	"fmt"
	"net/http"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/require"
)

// Feature: Archive admission
//
// Scenario: Retrying a submission does not start another archive
// Given an accepted archive request
//
// # When the client retries that request with the same idempotency key
//
// Then the original archive admission is returned
func TestArchiveAdmission_RepeatedSubmissionReturnsOriginalArchive(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("repeated-submission"),
	)

	firstResponse := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		requestBody,
		headers,
	)

	require.Equal(
		t,
		http.StatusAccepted,
		firstResponse.Status,
	)

	firstAccepted := testutil.Decode[contracts.ArchiveAccepted](t, firstResponse)

	require.NotEmpty(t, firstAccepted.ArchiveID)

	retryResponse := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		requestBody,
		headers,
	)

	require.Equal(
		t,
		http.StatusAccepted,
		retryResponse.Status,
	)

	retryAccepted := testutil.Decode[contracts.ArchiveAccepted](t, retryResponse)
	require.Equal(
		t,
		firstAccepted,
		retryAccepted,
	)
}
