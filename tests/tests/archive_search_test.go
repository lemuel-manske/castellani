package tests

import (
	"encoding/json"
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

type archiveSearchResponse struct {
	Results []struct {
		ArchiveID  string `json:"archiveId"`
		SnapshotID string `json:"snapshotId"`
		URL        string `json:"url"`
		Snippet    string `json:"snippet"`
	} `json:"results"`
}

// Feature: Archive search
//
// Scenario: Search the snapshots of a published archive
// Given an archive has completed successfully
//
// When a client searches for text present in the captured fixture
//
// Then the search result references a snapshot in that archive
func TestArchiveSearch_FindsPublishedSnapshot(t *testing.T) {
	services := infra.Start(t)

	requestBody := fmt.Sprintf(
		`{"seedUrl":%q,"maxDepth":1,"maxPages":3}`,
		fixtureSiteURL+"/index.html",
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
	require.Equal(t, http.StatusAccepted, response.Status)

	accepted := testutil.Decode[contracts.ArchiveAccepted](t, response)
	status := testutil.WaitForArchiveTerminalState(
		t,
		services.Gateway.BaseURL(),
		accepted.StatusURL,
		archiveTimeout,
	)
	require.Equal(t, "COMPLETED", status.Status)

	searchPath := fmt.Sprintf(
		"/search?q=%s&archiveId=%s&limit=10",
		url.QueryEscape("deterministic"),
		url.QueryEscape(accepted.ArchiveID),
	)

	var search archiveSearchResponse
	require.Eventually(
		t,
		func() bool {
			searchResponse := testutil.Get(t, services.Gateway.BaseURL(), searchPath)
			if searchResponse.Status != http.StatusOK {
				return false
			}

			return json.Unmarshal([]byte(searchResponse.Body), &search) == nil &&
				len(search.Results) > 0
		},
		archiveTimeout,
		500*time.Millisecond,
		"search did not return results for archive %s",
		accepted.ArchiveID,
	)

	for _, result := range search.Results {
		require.Equal(t, accepted.ArchiveID, result.ArchiveID)
		require.NotEmpty(t, result.SnapshotID)
		require.NotEmpty(t, result.URL)
		require.NotEmpty(t, result.Snippet)
	}
}
