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
// Scenario: Finding a published snapshot by its text
// Given an archive containing searchable page text
//
// # When a client searches for that text
//
// Then the result references a snapshot in that archive
func TestArchiveSearch_FindsPublishedSnapshot(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-happy-path"),
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
		"archive status: %+v",
		status,
	)

	searchPath := fmt.Sprintf(
		"/search?q=%s&archiveId=%s&limit=10",
		url.QueryEscape("deterministic"),
		url.QueryEscape(accepted.ArchiveID),
	)

	search := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(searchPath),
		ArchiveTimeout,
	)

	result := search.Results[0]

	require.Equal(
		t,
		accepted.ArchiveID,
		result.ArchiveID,
	)

	require.NotEmpty(t, result.SnapshotID)
	require.NotEmpty(t, result.URL)
	require.NotEmpty(t, result.Snippet)
}

// Feature: Archive search
//
// Scenario: Reading a documented search result
// Given a published archive with a searchable page
//
// # When a client searches within that archive
//
// Then the result includes its identifiers, URL, capture time, and snippet
func TestArchiveSearch_ResultsUseDocumentedSchema(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":0,"maxPages":1}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-schema"),
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

	results := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
		)),
		ArchiveTimeout,
	)

	require.Len(
		t,
		results.Results,
		1,
	)

	testutil.RequireSearchResultsSchema(
		t,
		results,
		10,
	)
}

// Feature: Archive search
//
// Scenario: Finding published content without a scope filter
// Given a published page containing a distinctive phrase
//
// # When a client searches without an archive or collection filter
//
// Then the result refers to that published page
func TestArchiveSearch_UnfilteredQueryFindsPublishedPage(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/unsafe.html","maxDepth":0,"maxPages":1}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("search-unfiltered"),
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

	results := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&limit=10",
			url.QueryEscape("unsafe-marker-phrase"),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, results.Results)
	require.Equal(
		t,
		"http://fixture-site/unsafe.html",
		results.Results[0].URL,
	)
}
