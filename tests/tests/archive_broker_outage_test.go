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

// Feature: Archive lifecycle
//
// Scenario: Recovering admission while message delivery is unavailable
// Given a website to archive
//
// # When the archive is admitted while the broker is unavailable
//
// Then the run completes after delivery recovers
// And each logical page is committed once
func TestArchive_OutboxDrainsAfterBrokerOutage(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("broker-outage"),
	)

	var accepted contracts.ArchiveAccepted

	services.WithServiceStopped(
		t,
		services.RabbitMQ,
		func() {
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

		accepted = testutil.Decode[contracts.ArchiveAccepted](t, response)
	},
	)

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
	require.Zero(t, status.Capture.Failed)

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

	testutil.RequireDistinctCapturedPages(t, pages.Items)

	testutil.RequireCapturedPageURLs(
		t,
		pages.Items,
		[]string{
			"http://fixture-site/index.html",
			"http://fixture-site/about.html",
			"http://fixture-site/docs.html",
		},
	)
}
