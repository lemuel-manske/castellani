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
// Scenario: Following an archive from admission to publication
// Given a website whose pages can be crawled
//
// # When a client monitors an archive of that website
//
// Then the archive advances through its lifecycle states in order
// And it ends published with all pages captured
func TestArchive_Polling_ShowsLifecycleProgression(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("lifecycle-progression"),
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

	require.NotEmpty(t, accepted.StatusURL)

	progression := testutil.WaitForArchiveStatusProgression(
		t,
		services.Gateway.URL(accepted.StatusURL),
		ArchiveTimeout,
	)

	require.True(
		t,
		progression.CaptureIncreased,
	)

	require.Equal(
		t,
		"COMPLETED",
		progression.Observed[len(progression.Observed)-1],
	)

	require.True(
		t,
		progression.Ordered,
	)

	require.Equal(
		t,
		"PUBLISH",
		progression.Final.Decision,
	)
	require.Equal(
		t,
		"READY",
		progression.Final.Replay.Status,
	)

	require.Equal(
		t,
		3,
		progression.Final.Capture.Captured,
	)

	require.Zero(t, progression.Final.Capture.Failed)
}
