package tests

import (
	"fmt"
	"net/http"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/require"
)

// Feature: Archive delivery
//
// Scenario: Retrieving part of a published WACZ
// Given a published archive
//
// # When a client requests the first four bytes of its WACZ
//
// Then the package returns exactly the requested byte range
func TestArchiveDelivery_ReturnsWACZByteRange(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("byte-range"),
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

	require.NotEmpty(t, accepted.ArchiveID)

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

	waczURL := fmt.Sprintf("/archives/%s/wacz", accepted.ArchiveID)

	waczResponse := testutil.GetWithHeaders(
		t,
		services.Gateway.URL(waczURL),
		"Range: bytes=0-3",
	)

	require.Equal(
		t,
		http.StatusPartialContent,
		waczResponse.Status,
	)

	require.True(
		t,
		strings.HasPrefix(waczResponse.Header.Get("Content-Range"), "bytes 0-3/"),
	)

	require.Equal(
		t,
		"application/wacz",
		waczResponse.Header.Get(HeaderContentType),
	)

	require.Equal(
		t,
		ZipPrefix,
		waczResponse.Body,
	)
}
