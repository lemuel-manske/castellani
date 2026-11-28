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

// Feature: Archive crawl limits
//
// Scenario: A crawl respects its page budget
// Given a website with more discoverable pages than the requested limit
//
// # When a client archives that website with a maximum of two pages
//
// Then exactly two distinct pages are captured
// And the archive completes successfully
func TestArchive_CrawlLimit_AdmitsOnlyAllowedPages(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":2}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("crawl-limit"),
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

	require.Equal(t, 2, status.Capture.Captured)

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

	require.Len(t, pages.Items, 2)

	testutil.RequireDistinctCapturedPages(t, pages.Items)
}
