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

// Feature: Archive lifecycle
//
// Scenario: Surviving a gateway restart during publication
// Given an admitted archive with linked pages
//
// # When the gateway is restarted while the run is active
//
// Then the same status URL reports completion
// And the published page remains searchable
func TestArchive_GatewayRestart_PreservesRun(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("gateway-restart"),
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

	running := testutil.WaitForArchiveStatus(
		t,
		services.Gateway.URL(accepted.StatusURL),
		"RUNNING",
		ArchiveTimeout,
	)

	require.Equal(t, accepted.ArchiveID, running.ArchiveID)

	services.RestartService(t, services.Gateway)

	status := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.URL(accepted.StatusURL),
		ArchiveTimeout,
	)

	require.Equal(t, "COMPLETED", status.Status)

	results := testutil.WaitForArchiveSearchResults(
		t,
		services.Gateway.URL(fmt.Sprintf(
			"/search?q=%s&archiveId=%s&limit=10",
			url.QueryEscape("deterministic"),
			url.QueryEscape(accepted.ArchiveID),
		)),
		ArchiveTimeout,
	)

	require.NotEmpty(t, results.Results)

	testutil.RequireSearchResultsForArchive(t, results, accepted.ArchiveID)
}
