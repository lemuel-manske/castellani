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
// Scenario: Retrieve a byte range from a published WACZ
// Given an archive has been successfully published
//
// When a client requests the first four bytes of its WACZ
//
// Then the server returns the requested partial content
func TestArchiveDelivery_ReturnsWACZByteRange(t *testing.T) {
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
			testutil.HeaderIdempotencyKey: "archive-range-0001",
		},
	)
	require.Equal(t, http.StatusAccepted, response.Status)

	accepted := testutil.Decode[contracts.ArchiveAccepted](t, response)
	require.NotEmpty(t, accepted.ArchiveID)

	status := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.BaseURL(),
		accepted.StatusURL,
		archiveTimeout,
	)
	require.Equal(t, "COMPLETED", status.Status)

	waczResponse := testutil.Send(
		t,
		http.MethodGet,
		services.Gateway.BaseURL(),
		fmt.Sprintf("/archives/%s/wacz", accepted.ArchiveID),
		"",
		map[string]string{"Range": "bytes=0-3"},
	)

	require.Equal(t, http.StatusPartialContent, waczResponse.Status)
	require.True(
		t,
		strings.HasPrefix(waczResponse.Header.Get("Content-Range"), "bytes 0-3/"),
		"unexpected Content-Range: %q",
		waczResponse.Header.Get("Content-Range"),
	)
	require.Equal(t, "application/wacz", waczResponse.Header.Get(testutil.HeaderContentType))
	require.Equal(t, zipPrefix, waczResponse.Body)
}
