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
	snapshotURL string,
	archiveID string,
	page contracts.PageOutcome,
) {
	t.Helper()

	require.Equal(
		t,
		"CAPTURED",
		page.Status,
	)
	require.NotEmpty(t, page.SnapshotID)

	snapshotResponse := testutil.Get(t, snapshotURL)

	require.Equal(
		t,
		http.StatusOK,
		snapshotResponse.Status,
	)

	snapshot := testutil.Decode[contracts.Snapshot](t, snapshotResponse)

	require.Equal(
		t,
		archiveID,
		snapshot.ArchiveID,
	)

	require.Equal(
		t,
		page.SnapshotID,
		snapshot.SnapshotID,
	)

	require.Equal(
		t,
		page.URL,
		snapshot.URL,
	)
}

// Feature: Archive pages
//
// Scenario: Browsing every captured page of an archive
// Given an archive with several captured pages
//
// # When a client lists the pages two at a time
//
// Then the first response includes a cursor to the remaining pages
// And following the cursor returns the final page without duplicates
// And each captured page resolves to its committed snapshot
func TestArchivePages_PaginatesCapturedPages(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("pages-pagination"),
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

	getURL := fmt.Sprintf("/archives/%s/pages?limit=2", accepted.ArchiveID)

	firstPage := testutil.Get(
		t,
		services.Gateway.URL(getURL),
	)

	require.Equal(
		t,
		http.StatusOK,
		firstPage.Status,
	)

	first := testutil.Decode[contracts.ArchivePages](t, firstPage)

	require.Len(
		t,
		first.Items,
		2,
	)
	require.NotNil(t, first.NextCursor)
	require.NotEmpty(t, *first.NextCursor)

	getURL = fmt.Sprintf("/archives/%s/pages?limit=2&cursor=%s",
		accepted.ArchiveID,
		url.QueryEscape(*first.NextCursor),
	)

	secondPage := testutil.Get(
		t,
		services.Gateway.URL(getURL),
	)

	require.Equal(
		t,
		http.StatusOK,
		secondPage.Status,
	)

	second := testutil.Decode[contracts.ArchivePages](t, secondPage)

	require.Len(
		t,
		second.Items,
		1,
	)
	require.Nil(t, second.NextCursor)

	firstPageOne := first.Items[0]
	firstPageTwo := first.Items[1]
	secondPageOne := second.Items[0]

	require.NotEqual(
		t,
		firstPageOne.URL,
		firstPageTwo.URL,
	)

	require.NotEqual(
		t,
		firstPageOne.URL,
		secondPageOne.URL,
	)

	require.NotEqual(
		t,
		firstPageTwo.URL,
		secondPageOne.URL,
	)

	requirePageSnapshot(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/archives/%s/snapshots/%s",
			accepted.ArchiveID,
			url.PathEscape(firstPageOne.SnapshotID),
		)),
		accepted.ArchiveID,
		firstPageOne,
	)

	requirePageSnapshot(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/archives/%s/snapshots/%s",
			accepted.ArchiveID,
			url.PathEscape(firstPageTwo.SnapshotID),
		)),
		accepted.ArchiveID,
		firstPageTwo,
	)

	requirePageSnapshot(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/archives/%s/snapshots/%s",
			accepted.ArchiveID,
			url.PathEscape(secondPageOne.SnapshotID),
		)),
		accepted.ArchiveID,
		secondPageOne,
	)
}
