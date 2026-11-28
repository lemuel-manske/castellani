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

// Feature: Archive re-archiving
//
// Scenario: Re-archiving a website creates distinct historical snapshots
// Given the same website archived twice with separate requests
//
// # When both archives complete
//
// Then each run has a distinct archive and snapshot identity
// And both snapshots remain retrievable and searchable
func TestArchive_Rearchiving_PreservesDistinctSnapshots(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	firstHeaders := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("rearchive-first"),
	)

	firstResponse := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		requestBody,
		firstHeaders,
	)

	require.Equal(
		t,
		http.StatusAccepted,
		firstResponse.Status,
	)

	firstAccepted := testutil.Decode[contracts.ArchiveAccepted](t, firstResponse)

	secondHeaders := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("rearchive-second"),
	)

	secondResponse := testutil.Post(
		t,
		services.Gateway.URL("/archives"),
		requestBody,
		secondHeaders,
	)

	require.Equal(
		t,
		http.StatusAccepted,
		secondResponse.Status,
	)

	secondAccepted := testutil.Decode[contracts.ArchiveAccepted](t, secondResponse)

	require.NotEqual(
		t,
		firstAccepted.ArchiveID,
		secondAccepted.ArchiveID,
	)

	firstStatus := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.URL(firstAccepted.StatusURL),
		ArchiveTimeout,
	)

	secondStatus := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.URL(secondAccepted.StatusURL),
		ArchiveTimeout,
	)

	require.Equal(
		t,
		"COMPLETED",
		firstStatus.Status,
	)
	require.Equal(
		t,
		"COMPLETED",
		secondStatus.Status,
	)

	firstPagesResponse := testutil.Get(
		t,
		services.Gateway.URL(
			fmt.Sprintf("/archives/%s/pages?limit=10", firstAccepted.ArchiveID),
		),
	)

	require.Equal(
		t,
		http.StatusOK,
		firstPagesResponse.Status,
	)

	secondPagesResponse := testutil.Get(
		t,
		services.Gateway.URL(
			fmt.Sprintf("/archives/%s/pages?limit=10", secondAccepted.ArchiveID),
		),
	)

	require.Equal(
		t,
		http.StatusOK,
		secondPagesResponse.Status,
	)

	firstPages := testutil.Decode[contracts.ArchivePages](t, firstPagesResponse)
	secondPages := testutil.Decode[contracts.ArchivePages](t, secondPagesResponse)

	require.Len(
		t,
		firstPages.Items,
		3,
	)
	require.Len(
		t,
		secondPages.Items,
		3,
	)

	testutil.RequireDistinctCapturedPages(t, firstPages.Items)
	testutil.RequireDistinctCapturedPages(t, secondPages.Items)

	firstPage := firstPages.Items[0]
	secondPage := secondPages.Items[0]

	require.Equal(
		t,
		firstPage.URL,
		secondPage.URL,
	)
	require.NotEqual(
		t,
		firstPage.SnapshotID,
		secondPage.SnapshotID,
	)

	firstSnapshot := testutil.Get(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/archives/%s/snapshots/%s",
			firstAccepted.ArchiveID,
			url.PathEscape(firstPage.SnapshotID),
		)),
	)

	require.Equal(
		t,
		http.StatusOK,
		firstSnapshot.Status,
	)

	secondSnapshot := testutil.Get(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/archives/%s/snapshots/%s",
			secondAccepted.ArchiveID,
			url.PathEscape(secondPage.SnapshotID),
		)),
	)

	require.Equal(
		t,
		http.StatusOK,
		secondSnapshot.Status,
	)

	firstMetadata := testutil.Decode[contracts.Snapshot](t, firstSnapshot)
	secondMetadata := testutil.Decode[contracts.Snapshot](t, secondSnapshot)

	require.Equal(
		t,
		firstAccepted.ArchiveID,
		firstMetadata.ArchiveID,
	)
	require.Equal(
		t,
		secondAccepted.ArchiveID,
		secondMetadata.ArchiveID,
	)
	require.Equal(
		t,
		firstPage.SnapshotID,
		firstMetadata.SnapshotID,
	)
	require.Equal(
		t,
		secondPage.SnapshotID,
		secondMetadata.SnapshotID,
	)
	require.NotEmpty(t, firstMetadata.CapturedAt)
	require.NotEmpty(t, secondMetadata.CapturedAt)
	require.NotEqual(
		t,
		firstMetadata.CapturedAt,
		secondMetadata.CapturedAt,
	)

	firstSearch := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&snapshotId=%s&limit=10",
			url.QueryEscape("fixture"),
			url.QueryEscape(firstPage.SnapshotID),
		)),
		ArchiveTimeout,
	)

	secondSearch := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&snapshotId=%s&limit=10",
			url.QueryEscape("fixture"),
			url.QueryEscape(secondPage.SnapshotID),
		)),
		ArchiveTimeout,
	)

	require.Equal(
		t,
		firstAccepted.ArchiveID,
		firstSearch.Results[0].ArchiveID,
	)
	require.Equal(
		t,
		firstPage.SnapshotID,
		firstSearch.Results[0].SnapshotID,
	)
	require.Equal(
		t,
		firstMetadata.CapturedAt,
		firstSearch.Results[0].CapturedAt,
	)

	require.Equal(
		t,
		secondAccepted.ArchiveID,
		secondSearch.Results[0].ArchiveID,
	)
	require.Equal(
		t,
		secondPage.SnapshotID,
		secondSearch.Results[0].SnapshotID,
	)
	require.Equal(
		t,
		secondMetadata.CapturedAt,
		secondSearch.Results[0].CapturedAt,
	)
}
