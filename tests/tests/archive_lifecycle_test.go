package tests

import (
	"fmt"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/lemuel-manske/castellani/tests/internal/infra"
	"github.com/lemuel-manske/castellani/tests/internal/testutil"
	"github.com/stretchr/testify/require"
)

const (
	fixtureSiteURL = "http://fixture-site"
	archiveTimeout = 3 * time.Minute
)

func TestArchiveLifecycle_CompletesSuccessfully(t *testing.T) {
	services := infra.Start(t)

	requestBody := fmt.Sprintf(
		`{"seedUrl":%q,"maxDepth":1,"maxPages":3}`,
		fixtureSiteURL+"/index.html",
	)

	acceptedResponse := testutil.Post(
		t,
		services.Gateway.BaseURL(),
		"/archives",
		requestBody,
		map[string]string{
			testutil.HeaderContentType:    testutil.ContentTypeJSON,
			testutil.HeaderIdempotencyKey: "archive-happy-path-0001",
		},
	)

	require.Equal(t, http.StatusAccepted, acceptedResponse.Status)

	accepted := testutil.Decode[contracts.ArchiveAccepted](t, acceptedResponse)
	require.NotEmpty(t, accepted.ArchiveID)
	require.Equal(t, "ACCEPTED", accepted.Status)

	var (
		statusResponse testutil.Result
		archiveStatus  contracts.ArchiveStatus
	)

	require.Eventually(
		t,
		func() bool {
			statusResponse = testutil.Get(
				t,
				services.Gateway.BaseURL(),
				accepted.StatusURL,
			)

			if statusResponse.Status != http.StatusOK {
				return false
			}

			archiveStatus = testutil.Decode[contracts.ArchiveStatus](t, statusResponse)

			switch archiveStatus.Status {
			case "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED":
				return true
			default:
				return false
			}
		},
		archiveTimeout,
		500*time.Millisecond,
		"archive did not reach a terminal state; last response: %s",
		statusResponse.Body,
	)

	require.Equal(t, accepted.ArchiveID, archiveStatus.ArchiveID)
	require.Equal(t, "COMPLETED", archiveStatus.Status)
	require.Equal(t, 3, archiveStatus.Capture.Captured)
	require.Zero(t, archiveStatus.Capture.Failed)
	require.Zero(t, archiveStatus.Capture.Pending)
	require.Equal(t, "READY", archiveStatus.Replay.Status)

	pagesResponse := testutil.Get(
		t,
		services.Gateway.BaseURL(),
		fmt.Sprintf("/archives/%s/pages", accepted.ArchiveID),
	)
	require.Equal(t, http.StatusOK, pagesResponse.Status)

	pages := testutil.Decode[contracts.ArchivePages](t, pagesResponse)
	require.Len(t, pages.Items, 3)

	expectedURLs := []string{
		fixtureSiteURL + "/index.html",
		fixtureSiteURL + "/about.html",
		fixtureSiteURL + "/docs.html",
	}

	actualURLs := make([]string, 0, len(pages.Items))

	for _, page := range pages.Items {
		require.Equal(t, "CAPTURED", page.Status)
		require.NotEmpty(t, page.SnapshotID)
		actualURLs = append(actualURLs, page.URL)

		snapshotResponse := testutil.Get(
			t,
			services.Gateway.BaseURL(),
			fmt.Sprintf(
				"/archives/%s/snapshots/%s",
				accepted.ArchiveID,
				page.SnapshotID,
			),
		)
		require.Equal(t, http.StatusOK, snapshotResponse.Status)

		snapshot := testutil.Decode[contracts.Snapshot](t, snapshotResponse)
		require.Equal(t, accepted.ArchiveID, snapshot.ArchiveID)
		require.Equal(t, page.SnapshotID, snapshot.SnapshotID)
		require.Equal(t, page.URL, snapshot.URL)
	}

	require.ElementsMatch(t, expectedURLs, actualURLs)

	waczPath := fmt.Sprintf("/archives/%s/wacz", accepted.ArchiveID)

	headResponse := testutil.Send(
		t,
		http.MethodHead,
		services.Gateway.BaseURL(),
		waczPath,
		"",
		nil,
	)
	require.Equal(t, http.StatusOK, headResponse.Status)
	require.Equal(t, "bytes", headResponse.Header.Get("Accept-Ranges"))
	require.NotEmpty(t, headResponse.Header.Get("ETag"))
	require.NotEmpty(t, headResponse.Header.Get("Content-Length"))

	waczResponse := testutil.Get(t, services.Gateway.BaseURL(), waczPath)
	require.Equal(t, http.StatusOK, waczResponse.Status)
	require.Equal(t, "application/wacz", waczResponse.Header.Get(testutil.HeaderContentType))
	require.True(
		t,
		strings.HasPrefix(waczResponse.Body, "\x50\x4b\x03\x04"),
		"published WACZ should be a ZIP archive",
	)
}
