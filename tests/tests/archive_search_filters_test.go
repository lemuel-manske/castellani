package tests

import (
	"fmt"
	"net/http"
	"net/url"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/require"
)

// Feature: Archive search
//
// Scenario: Restricting results to one collection
// Given an archive submitted in a named collection
//
// # When a client filters a query by that collection
//
// Then results are limited to that collection
// And a different collection filter yields nothing
func TestArchiveSearch_FiltersByCollection(t *testing.T) {
	services := infra.Start(t)

	collectionID := services.IdempotencyKey("search-collection-filter")

	requestBody := fmt.Sprintf(
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":0,"maxPages":1,"collectionId":%q}`,
		collectionID,
	)

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		collectionID,
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

	results := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&collectionId=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
			url.QueryEscape(collectionID),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, results.Results)

	testutil.RequireSearchResultsForArchive(t, results, accepted.ArchiveID)

	otherResponse := testutil.Get(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&collectionId=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
			url.QueryEscape(collectionID+"-other"),
		)),
	)

	require.Equal(
		t,
		http.StatusOK,
		otherResponse.Status,
	)

	other := testutil.Decode[contracts.SearchResults](t, otherResponse)

	require.Empty(t, other.Results)
}

// Feature: Archive search
//
// Scenario: Restricting results to one snapshot
// Given an archive with a captured snapshot
//
// # When a client filters a query by that snapshot
//
// Then the result refers to that snapshot only
func TestArchiveSearch_FiltersBySnapshot(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-snapshot-filter"),
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

	pagesResponse := testutil.Get(
		t,
		services.Gateway.URL(
			fmt.Sprintf("/archives/%s/pages?limit=1", accepted.ArchiveID),
		),
	)

	require.Equal(
		t,
		http.StatusOK,
		pagesResponse.Status,
	)

	pages := testutil.Decode[contracts.ArchivePages](t, pagesResponse)

	require.Len(t, pages.Items, 1)

	snapshotID := pages.Items[0].SnapshotID

	results := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&snapshotId=%s&limit=10",
			url.QueryEscape("fixture"),
			url.QueryEscape(snapshotID),
		)),
		ArchiveTimeout,
	)

	require.Len(t, results.Results, 1)

	testutil.RequireSearchResultsForSnapshot(t, results, snapshotID)
}

// Feature: Archive search
//
// Scenario: Restricting results to snapshots captured from a time
// Given a published archive with a captured snapshot
//
// # When a client filters a query by a time at or before that capture
//
// Then the snapshot is returned
// And a later bound excludes it
func TestArchiveSearch_FiltersByCapturedFrom(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":0,"maxPages":1}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-captured-from"),
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

	scoped := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, scoped.Results)

	from, to := testutil.SearchCapturedAtBounds(t, scoped.Results)

	earliest, err := time.Parse(time.RFC3339Nano, from)
	require.NoError(t, err)

	latest, err := time.Parse(time.RFC3339Nano, to)
	require.NoError(t, err)

	inclusiveFrom := earliest.Add(-time.Second).Format(time.RFC3339Nano)
	exclusiveFrom := latest.Add(time.Second).Format(time.RFC3339Nano)

	results := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&capturedFrom=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
			url.QueryEscape(inclusiveFrom),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, results.Results)

	testutil.RequireSearchCapturedAtWithin(t, results, from, to)

	excludedResponse := testutil.Get(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&capturedFrom=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
			url.QueryEscape(exclusiveFrom),
		)),
	)

	require.Equal(
		t,
		http.StatusOK,
		excludedResponse.Status,
	)

	excluded := testutil.Decode[contracts.SearchResults](t, excludedResponse)

	require.Empty(t, excluded.Results)
}

// Feature: Archive search
//
// Scenario: Restricting results to snapshots captured up to a time
// Given a published archive with a captured snapshot
//
// # When a client filters a query by a time at or after that capture
//
// Then the snapshot is returned
// And an earlier bound excludes it
func TestArchiveSearch_FiltersByCapturedTo(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":0,"maxPages":1}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-captured-to"),
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

	scoped := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, scoped.Results)

	from, to := testutil.SearchCapturedAtBounds(t, scoped.Results)

	earliest, err := time.Parse(time.RFC3339Nano, from)
	require.NoError(t, err)

	latest, err := time.Parse(time.RFC3339Nano, to)
	require.NoError(t, err)

	inclusiveTo := latest.Add(time.Second).Format(time.RFC3339Nano)
	exclusiveTo := earliest.Add(-time.Second).Format(time.RFC3339Nano)

	results := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&capturedTo=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
			url.QueryEscape(inclusiveTo),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, results.Results)

	testutil.RequireSearchCapturedAtWithin(t, results, from, to)

	excludedResponse := testutil.Get(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&capturedTo=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
			url.QueryEscape(exclusiveTo),
		)),
	)

	require.Equal(
		t,
		http.StatusOK,
		excludedResponse.Status,
	)

	excluded := testutil.Decode[contracts.SearchResults](t, excludedResponse)

	require.Empty(t, excluded.Results)
}
