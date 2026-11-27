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

func requirePageSnapshot(
	t *testing.T,
	baseURL string,
	archiveID string,
	page contracts.PageOutcome,
) {
	t.Helper()

	require.Equal(t, "CAPTURED", page.Status)
	require.NotEmpty(t, page.SnapshotID)

	snapshotResponse := testutil.Get(
		t,
		baseURL,
		fmt.Sprintf(
			"/archives/%s/snapshots/%s",
			archiveID,
			url.PathEscape(page.SnapshotID),
		),
	)
	require.Equal(t, http.StatusOK, snapshotResponse.Status)

	snapshot := testutil.Decode[contracts.Snapshot](t, snapshotResponse)
	require.Equal(t, archiveID, snapshot.ArchiveID)
	require.Equal(t, page.SnapshotID, snapshot.SnapshotID)
	require.Equal(t, page.URL, snapshot.URL)
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
		"http://fixture-site/index.html",
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

	first := testutil.Decode[contracts.ArchivePages](t, firstPage)
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

	firstPageOne := first.Items[0]
	firstPageTwo := first.Items[1]
	secondPageOne := second.Items[0]

	require.NotEqual(t, firstPageOne.URL, firstPageTwo.URL)
	require.NotEqual(t, firstPageOne.URL, secondPageOne.URL)
	require.NotEqual(t, firstPageTwo.URL, secondPageOne.URL)

	requirePageSnapshot(t, services.Gateway.BaseURL(), accepted.ArchiveID, firstPageOne)
	requirePageSnapshot(t, services.Gateway.BaseURL(), accepted.ArchiveID, firstPageTwo)
	requirePageSnapshot(t, services.Gateway.BaseURL(), accepted.ArchiveID, secondPageOne)
}
