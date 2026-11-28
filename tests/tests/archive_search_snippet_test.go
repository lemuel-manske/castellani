package tests

import (
	"fmt"
	"net/http"
	"net/url"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/require"
)

// Feature: Archive search
//
// Scenario: Search snippets render captured markup as plain text
// Given a captured page containing literal script and event-handler markup
//
// # When a client searches for a phrase on that page
//
// Then the snippet contains no executable HTML
// And still includes the matching text
func TestArchiveSearch_SnippetIsSafeHtml(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/unsafe.html","maxDepth":0,"maxPages":1}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("unsafe-snippet"),
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

	require.Equal(t, "COMPLETED", status.Status)

	search := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&limit=10",
			url.QueryEscape("unsafe-marker-phrase"),
			url.QueryEscape(accepted.ArchiveID),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, search.Results)

	result := search.Results[0]

	require.Equal(t, accepted.ArchiveID, result.ArchiveID)
	require.Equal(t, "http://fixture-site/unsafe.html", result.URL)

	testutil.RequireSafeSnippet(t, result.Snippet, "unsafe")
}
