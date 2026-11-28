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

// Feature: Archive lifecycle
//
// Scenario: Capturing each page once with competing workers
// Given three capture workers consuming the same page queue
//
// # When a client archives a website with linked pages
//
// Then each logical page is committed once
// And the capture counters match the fixture
func TestArchive_CompetingConsumers_CaptureEachPageOnce(t *testing.T) {
	services := infra.Start(t)

	require.Len(
		t,
		services.CaptureWorkers,
		3,
	)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("competing-consumers"),
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

	getURL := fmt.Sprintf("/archives/%s/pages?limit=10", accepted.ArchiveID)

	pagesResponse := testutil.Get(
		t,
		services.Gateway.URL(getURL),
	)

	require.Equal(
		t,
		http.StatusOK,
		pagesResponse.Status,
	)

	pages := testutil.Decode[contracts.ArchivePages](t, pagesResponse)

	require.Len(
		t,
		pages.Items,
		3,
	)

	testutil.RequireDistinctCapturedPages(t, pages.Items)

	testutil.RequireCapturedPageURLs(
		t,
		pages.Items,
		[]string{
			"http://fixture-site/index.html",
			"http://fixture-site/about.html",
			"http://fixture-site/docs.html",
		},
	)
}
