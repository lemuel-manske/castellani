package testutil

import (
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/stretchr/testify/require"
)

func WaitForArchiveSearchResults(
	t *testing.T,
	url string,
	timeout time.Duration,
) contracts.SearchResults {
	t.Helper()

	return WaitForArchiveSearchResultsAtLeast(t, url, timeout, 1)
}

func WaitForArchiveSearchResultsAtLeast(
	t *testing.T,
	url string,
	timeout time.Duration,
	minimum int,
) contracts.SearchResults {
	t.Helper()

	var results contracts.SearchResults

	require.Eventually(
		t,
		func() bool {
			response := Get(t, url)

			if response.Status != http.StatusOK {
				return false
			}

			results = Decode[contracts.SearchResults](t, response)

			return len(results.Results) >= minimum
		},
		timeout,
		500*time.Millisecond,
		"search did not return at least %d results for %s",
		minimum,
		url,
	)

	return results
}

func RequireSearchResultsSchema(
	t *testing.T,
	results contracts.SearchResults,
	limit int,
) {
	t.Helper()

	require.LessOrEqual(t, len(results.Results), limit)

	for _, result := range results.Results {
		require.NotEmpty(t, result.ArchiveID)
		require.NotEmpty(t, result.SnapshotID)
		require.NotEmpty(t, result.URL)
		require.NotEmpty(t, result.CapturedAt)
		require.NotEmpty(t, result.Snippet)

		_, err := time.Parse(time.RFC3339Nano, result.CapturedAt)
		require.NoError(t, err)
	}
}

func RequireSearchResultsForArchive(
	t *testing.T,
	results contracts.SearchResults,
	archiveID string,
) {
	t.Helper()

	for _, result := range results.Results {
		require.Equal(t, archiveID, result.ArchiveID)
	}
}

func RequireSearchResultsForSnapshot(
	t *testing.T,
	results contracts.SearchResults,
	snapshotID string,
) {
	t.Helper()

	for _, result := range results.Results {
		require.Equal(t, snapshotID, result.SnapshotID)
	}
}

func SearchCapturedAtBounds(
	t *testing.T,
	results []contracts.SearchResult,
) (string, string) {
	t.Helper()

	require.NotEmpty(t, results)

	earliest, err := time.Parse(time.RFC3339Nano, results[0].CapturedAt)
	require.NoError(t, err)

	latest := earliest
	from := results[0].CapturedAt
	to := results[0].CapturedAt

	for _, result := range results[1:] {
		capturedAt, err := time.Parse(time.RFC3339Nano, result.CapturedAt)
		require.NoError(t, err)

		if capturedAt.Before(earliest) {
			earliest = capturedAt
			from = result.CapturedAt
		}

		if capturedAt.After(latest) {
			latest = capturedAt
			to = result.CapturedAt
		}
	}

	return from, to
}

func RequireSearchCapturedAtWithin(
	t *testing.T,
	results contracts.SearchResults,
	from string,
	to string,
) {
	t.Helper()

	earliest, err := time.Parse(time.RFC3339Nano, from)
	require.NoError(t, err)

	latest, err := time.Parse(time.RFC3339Nano, to)
	require.NoError(t, err)

	for _, result := range results.Results {
		capturedAt, err := time.Parse(time.RFC3339Nano, result.CapturedAt)
		require.NoError(t, err)

		require.False(
			t,
			capturedAt.Before(earliest),
			"capturedAt %s precedes %s",
			result.CapturedAt,
			from,
		)
		require.False(
			t,
			capturedAt.After(latest),
			"capturedAt %s follows %s",
			result.CapturedAt,
			to,
		)
	}
}

func RequireSafeSnippet(
	t *testing.T,
	snippet string,
	term string,
) {
	t.Helper()

	require.Contains(
		t,
		strings.ToLower(snippet),
		strings.ToLower(term),
	)
	require.NotContains(t, snippet, "<")
	require.NotContains(t, strings.ToLower(snippet), "onerror")
}
