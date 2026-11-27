package tests

import (
	"fmt"
	"net/http"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/require"
)

// Feature: Archive lifecycle
//
// Scenario: Successfully publish an archive
// Given the E2E stack and fixture website are running
//
// # When a client requests an archive of the website
//
// Then the archive completes with all expected pages captured
// And its WACZ is available for retrieval
func TestArchiveLifecycle_CompletesSuccessfully(t *testing.T) {
	services := infra.Start(t)

	requestBody := fmt.Sprintf(
		`{"seedUrl":%q,"maxDepth":1,"maxPages":3}`,
		"http://fixture-site/index.html",
	)

	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		requestBody,
		map[string]string{
			testutil.HeaderContentType:    testutil.ContentTypeJSON,
			testutil.HeaderIdempotencyKey: services.IdempotencyKey("happy-path"),
		},
	)

	require.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)

	accepted := testutil.Decode[contracts.ArchiveAccepted](t, response)
	require.NotEmpty(t, accepted.ArchiveID)

	status := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.BaseURL(),
		accepted.StatusURL,
		archiveTimeout,
	)

	require.Equal(
		t,
		"COMPLETED",
		status.Status,
		"archive status: %+v",
		status,
	)
	require.Equal(
		t,
		3,
		status.Capture.Captured,
	)
	require.Zero(t, status.Capture.Failed)
	require.Equal(
		t,
		"READY",
		status.Replay.Status,
	)

	waczResponse := testutil.Get(
		t,
		services.Gateway.BaseURL(),
		fmt.Sprintf("/archives/%s/wacz", accepted.ArchiveID),
	)

	require.Equal(
		t,
		http.StatusOK,
		waczResponse.Status,
	)
	require.Equal(
		t,
		"application/wacz",
		waczResponse.Header.Get(testutil.HeaderContentType),
	)
	require.True(
		t,
		strings.HasPrefix(waczResponse.Body, zipPrefix),
		"published WACZ should be a ZIP archive",
	)
}
