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

// Feature: Archive admission
//
// Scenario: An accepted archive can be checked immediately
// Given a website that can be archived
//
// # When a client submits an archive request
//
// Then the client receives a status URL for that archive
// And the status reports the archive as not yet replayable
func TestArchive_DurableAdmission_IsImmediatelyReadable(t *testing.T) {
	services := infra.Start(t)

	requestBody :=
		`{"seedUrl":"http://fixture-site/index.html","maxDepth":1,"maxPages":3}`

	headers := fmt.Sprintf(
		`Content-Type: application/json; Idempotency-Key: %s`,
		services.IdempotencyKey("durable-admission"),
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

	require.Equal(t, "ACCEPTED", accepted.Status)
	require.Equal(
		t,
		accepted.StatusURL,
		response.Header.Get(HeaderLocation),
	)
	require.NotEmpty(t, accepted.ArchiveID)

	statusResponse := testutil.Get(
		t,
		services.Gateway.URL(accepted.StatusURL),
	)

	require.Equal(
		t,
		http.StatusOK,
		statusResponse.Status,
	)

	status := testutil.Decode[contracts.ArchiveStatus](t, statusResponse)

	require.Equal(
		t,
		accepted.ArchiveID,
		status.ArchiveID,
	)

	require.Equal(
		t,
		"NOT_READY",
		status.Replay.Status,
	)
}
