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
// Scenario: Retry an archive submission with the same idempotency key
// Given an archive submission has been accepted
//
// When the client retries the same submission with the same idempotency key
//
// Then the original archive admission is returned
func TestArchiveAdmission_RepeatedSubmissionReturnsOriginalArchive(t *testing.T) {
	services := infra.Start(t)

	requestBody := fmt.Sprintf(
		`{"seedUrl":%q,"maxDepth":1,"maxPages":3}`,
		"http://fixture-site/index.html",
	)
	headers := map[string]string{
		testutil.HeaderContentType:    testutil.ContentTypeJSON,
		testutil.HeaderIdempotencyKey: "archive-idempotency-0001",
	}

	firstResponse := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		requestBody,
		headers,
	)
	require.Equal(t, http.StatusAccepted, firstResponse.Status)

	firstAccepted := testutil.Decode[contracts.ArchiveAccepted](t, firstResponse)
	require.NotEmpty(t, firstAccepted.ArchiveID)

	retryResponse := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		requestBody,
		headers,
	)
	require.Equal(t, http.StatusAccepted, retryResponse.Status)

	retryAccepted := testutil.Decode[contracts.ArchiveAccepted](t, retryResponse)
	require.Equal(t, firstAccepted, retryAccepted)
}
