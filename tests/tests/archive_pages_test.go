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

type archivePagesResponse struct {
	Items      []contracts.PageOutcome `json:"items"`
	NextCursor *string                 `json:"nextCursor"`
}

// Feature: Archive pages
//
// Scenario: Paginate through all captured pages and retrieve their snapshots
// Given an archive has completed with three captured pages
//
// When a client lists the pages with a limit of two
//
// Then the response contains a cursor for the remaining page
// And following the cursor returns the final page without duplicates
// And each captured page resolves to its committed snapshot
func TestArchivePages_PaginatesCapturedPages(t *testing.T) {
	services := infra.Start(t)

	requestBody := fmt.Sprintf(
		`{"seedUrl":%q,"maxDepth":1,"maxPages":3}`,
		fixtureSiteURL+"/index.html",
	)
	response := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		requestBody,
		map[string]string{
			testutil.HeaderContentType:    testutil.ContentTypeJSON,
			testutil.HeaderIdempotencyKey: "archive-pages-pagination-0001",
		},
	)
	require.Equal(t, http.StatusAccepted, response.Status)

	accepted := testutil.Decode[contracts.ArchiveAccepted](t, response)
	status := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.BaseURL(),
		accepted.StatusURL,
		archiveTimeout,
	)
	require.Equal(t, "COMPLETED", status.Status)
	require.Equal(t, 3, status.Capture.Captured)

	firstPage := testutil.Get(
		t,
		services.Gateway.BaseURL(),
		fmt.Sprintf("/archives/%s/pages?limit=2", accepted.ArchiveID),
	)
	require.Equal(t, http.StatusOK, firstPage.Status)

	first := testutil.Decode[archivePagesResponse](t, firstPage)
	require.Len(t, first.Items, 2)
	require.NotNil(t, first.NextCursor)
	require.NotEmpty(t, *first.NextCursor)

	secondPage := testutil.Get(
		t,
		services.Gateway.BaseURL(),
		fmt.Sprintf(
			"/archives/%s/pages?limit=2&cursor=%s",
			accepted.ArchiveID,
			url.QueryEscape(*first.NextCursor),
		),
	)
	require.Equal(t, http.StatusOK, secondPage.Status)

	second := testutil.Decode[archivePagesResponse](t, secondPage)
	require.Len(t, second.Items, 1)
	require.Nil(t, second.NextCursor)

	pages := append(first.Items, second.Items...)
	require.Len(t, pages, 3)

	seenURLs := make(map[string]struct{}, len(pages))
	for _, page := range pages {
		require.Equal(t, "CAPTURED", page.Status)
		require.NotEmpty(t, page.SnapshotID)
		_, exists := seenURLs[page.URL]
		require.False(t, exists, "duplicate page URL: %s", page.URL)
		seenURLs[page.URL] = struct{}{}

		snapshotResponse := testutil.Get(
			t,
			services.Gateway.BaseURL(),
			fmt.Sprintf(
				"/archives/%s/snapshots/%s",
				accepted.ArchiveID,
				url.PathEscape(page.SnapshotID),
			),
		)
		require.Equal(t, http.StatusOK, snapshotResponse.Status)

		snapshot := testutil.Decode[contracts.Snapshot](t, snapshotResponse)
		require.Equal(t, accepted.ArchiveID, snapshot.ArchiveID)
		require.Equal(t, page.SnapshotID, snapshot.SnapshotID)
		require.Equal(t, page.URL, snapshot.URL)
	}
}
