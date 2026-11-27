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
// Scenario: Search the snapshots of a published archive
// Given an archive has completed successfully
//
// # When a client searches for text present in the captured fixture
//
// Then the search result references a snapshot in that archive
func TestArchiveSearch_FindsPublishedSnapshot(t *testing.T) {
	services := infra.Start(t)

	t.Cleanup(func() {
		if !t.Failed() {
			return
		}

		for name, service := range map[string]infra.Service{
			"search":      services.Search,
			"capture":     services.Capture,
			"coordinator": services.Coordinator,
			"rabbitmq":    services.RabbitMQ,
			"opensearch":  services.OpenSearch,
		} {
			logs, err := service.Logs(t.Context())
			if err != nil {
				t.Logf("%s logs unavailable: %v", name, err)
				continue
			}

			t.Logf("%s container logs (last 64 KiB):\\n%s", name, logs)
		}
	})

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
			testutil.HeaderIdempotencyKey: "archive-search-happy-path-0001",
		},
	)
	require.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)

	accepted := testutil.Decode[contracts.ArchiveAccepted](t, response)
	status := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.BaseURL(),
		accepted.StatusURL,
		archiveTimeout,
	)
	require.Equal(
		t,
		"COMPLETED",
		status.Status,
	)

	searchPath := fmt.Sprintf(
		"/search?q=%s&archiveId=%s&limit=10",
		url.QueryEscape("deterministic"),
		url.QueryEscape(accepted.ArchiveID),
	)

	var search contracts.SearchResults

	require.Eventually(
		t,
		func() bool {
			statusResponse := testutil.Get(
				t,
				services.Gateway.BaseURL(),
				accepted.StatusURL,
			)

			if statusResponse.Status == http.StatusOK {
				status = testutil.Decode[contracts.ArchiveStatus](t, statusResponse)
			}

			response := testutil.Get(
				t,
				services.Gateway.BaseURL(),
				searchPath,
			)

			if response.Status != http.StatusOK {
				return false
			}

			result := testutil.Decode[contracts.SearchResults](t, response)
			search = result

			return len(result.Results) > 0
		},
		archiveTimeout,
		500*time.Millisecond,
		"search did not return results for archive %s (search status: %s, indexed: %d, expected: %d)",
		accepted.ArchiveID,
		status.Search.Status,
		status.Search.Indexed,
		status.Search.Expected,
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
