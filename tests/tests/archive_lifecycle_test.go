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
// Scenario: Publishing an archive of a website
// Given a website with linked pages
//
// # When a client requests an archive of that website
//
// Then the archive completes with every discoverable page captured
// And its WACZ is available for retrieval
func TestArchiveLifecycle_CompletesSuccessfully(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("happy-path"),
	)

	response := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		requestBody,
		headers,
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
		services.Gateway.URL(accepted.StatusURL),
		ArchiveTimeout,
	)

	require.Equal(
		t,
		"COMPLETED",
		status.Status,
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

	getURL := fmt.Sprintf("/archives/%s/wacz", accepted.ArchiveID)

	waczResponse := testutil.Get(
		t,
		services.Gateway.URL(getURL),
	)

	require.Equal(
		t,
		http.StatusOK,
		waczResponse.Status,
	)

	require.Equal(
		t,
		"application/wacz",
		waczResponse.Header.Get(HeaderContentType),
	)

	require.True(
		t,
		strings.HasPrefix(waczResponse.Body, ZipPrefix),
		"published WACZ should be a ZIP archive",
	)
}
