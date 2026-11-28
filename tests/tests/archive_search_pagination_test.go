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
// Scenario: Resuming search results with a cursor
// Given two published archives in one collection containing the same distinctive phrase
//
// # When a client requests the next page with a cursor
//
// Then the next page starts at a different snapshot
// And repeating the cursor returns the same page
func TestArchiveSearch_PaginatesPublishedResults(t *testing.T) {
	services := infra.Start(t)

	collectionID := services.IdempotencyKey("search-pagination")

	requestBody := fmt.Sprintf(
		`{"seedUrl":"http://fixture-site/unsafe.html","maxDepth":0,"maxPages":1,"collectionId":%q}`,
		collectionID,
	)

	firstHeaders := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-pagination-first"),
	)

	secondHeaders := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-pagination-second"),
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

	firstStatus := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.URL(firstAccepted.StatusURL),
		ArchiveTimeout,
	)

	require.Equal(
		t,
		"COMPLETED",
		firstStatus.Status,
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

	secondStatus := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.URL(secondAccepted.StatusURL),
		ArchiveTimeout,
	)

	require.Equal(
		t,
		"COMPLETED",
		secondStatus.Status,
	)

	phrase := url.QueryEscape("unsafe-marker-phrase")

	all := testutil.WaitForArchiveSearchResultsAtLeast(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&collectionId=%s&limit=10",
			phrase,
			url.QueryEscape(collectionID),
		)),
		ArchiveTimeout,
		2,
	)

	require.Len(
		t,
		all.Results,
		2,
	)

	first := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&collectionId=%s&limit=1",
			phrase,
			url.QueryEscape(collectionID),
		)),
		ArchiveTimeout,
	)

	require.Len(
		t,
		first.Results,
		1,
	)
	require.NotNil(t, first.NextCursor)

	secondURL := services.Gateway.URL(fmt.Sprintf(
		"/search?q=%s&collectionId=%s&limit=1&cursor=%s",
		phrase,
		url.QueryEscape(collectionID),
		url.QueryEscape(*first.NextCursor),
	))

	second := testutil.WaitForArchiveSearchResults(
		t,
		secondURL,
		ArchiveTimeout,
	)

	require.Len(
		t,
		second.Results,
		1,
	)
	require.NotEqual(
		t,
		first.Results[0].SnapshotID,
		second.Results[0].SnapshotID,
	)
	require.Contains(
		t,
		[]string{all.Results[0].SnapshotID, all.Results[1].SnapshotID},
		first.Results[0].SnapshotID,
	)
	require.Contains(
		t,
		[]string{all.Results[0].SnapshotID, all.Results[1].SnapshotID},
		second.Results[0].SnapshotID,
	)

	secondAgain := testutil.WaitForArchiveSearchResults(
		t,
		secondURL,
		ArchiveTimeout,
	)

	require.Equal(
		t,
		second,
		secondAgain,
	)
}
