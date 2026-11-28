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

// Feature: Archive WACZ packaging
//
// Scenario: A published archive preserves its captured evidence
// Given an archive with captured pages
//
// # When a client downloads its WACZ
//
// Then the package contains a data package descriptor and WARC records
// And every captured page has a matching WARC record
func TestArchive_Wacz_ContainsPublishedRecords(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("wacz-records"),
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

	waczURL := fmt.Sprintf("/archives/%s/wacz", accepted.ArchiveID)

	waczResponse := testutil.Get(
		t,
		services.Gateway.URL(waczURL),
	)

	require.Equal(
		t,
		http.StatusOK,
		waczResponse.Status,
	)

	descriptor := testutil.WaczDescriptor(t, waczResponse.Body)

	require.NotEmpty(t, descriptor)

	records := testutil.WaczRecords(t, waczResponse.Body)

	testutil.RequireWarcRecordsForPages(
		t,
		records,
		pages.Items,
	)
}

// Feature: Archive WACZ delivery
//
// Scenario: A published WACZ is immutable and byte-addressable
// Given a published archive
//
// # When a client requests its WACZ metadata and downloads it twice
//
// Then the package advertises byte-range support and a stable ETag
// And both downloads return identical bytes
func TestArchive_Wacz_DeliveryMetadataIsStable(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("wacz-metadata"),
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

	waczURL := services.Gateway.URL(
		fmt.Sprintf("/archives/%s/wacz", accepted.ArchiveID),
	)

	headResponse := testutil.Head(t, waczURL)

	require.Equal(
		t,
		http.StatusOK,
		headResponse.Status,
	)

	require.Equal(
		t,
		"bytes",
		headResponse.Header.Get("Accept-Ranges"),
	)

	require.NotEmpty(t, headResponse.Header.Get("ETag"))

	firstResponse := testutil.Get(t, waczURL)

	require.Equal(
		t,
		http.StatusOK,
		firstResponse.Status,
	)

	require.Equal(
		t,
		headResponse.Header.Get("ETag"),
		firstResponse.Header.Get("ETag"),
	)

	secondResponse := testutil.Get(t, waczURL)

	require.Equal(
		t,
		http.StatusOK,
		secondResponse.Status,
	)

	require.Equal(
		t,
		firstResponse.Body,
		secondResponse.Body,
	)

	require.Equal(
		t,
		firstResponse.Header.Get("Content-Length"),
		secondResponse.Header.Get("Content-Length"),
	)
}
