package testutil

import (
	"net/http"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/stretchr/testify/require"
)

type StatusProgression struct {
	Observed         []string
	Ordered          bool
	CaptureIncreased bool
	Final            contracts.ArchiveStatus
}

func WaitForArchiveTerminalState(
	t *testing.T,
	url string,
	timeout time.Duration,
) contracts.ArchiveStatus {
	t.Helper()

	var status contracts.ArchiveStatus
	require.Eventually(
		t,
		func() bool {
			response := Get(
				t,
				url,
			)

			if response.Status != http.StatusOK {
				return false
			}

			status = Decode[contracts.ArchiveStatus](t, response)

			switch status.Status {
			case "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED":
				return true
			default:
				return false
			}
		},
		timeout,
		500*time.Millisecond,
		"archive did not reach a terminal state",
	)

	return status
}

func WaitForArchiveStatusProgression(
	t *testing.T,
	url string,
	timeout time.Duration,
) StatusProgression {
	t.Helper()

	statusRanks := map[string]int{
		"ACCEPTED":     0,
		"RUNNING":      1,
		"FINALIZING":   2,
		"COMPENSATING": 2,
		"COMPLETED":    3,
	}

	progression := StatusProgression{
		Observed:         []string{"ACCEPTED"},
		Ordered:          true,
		CaptureIncreased: true,
	}

	var lastCaptured int

	require.Eventually(
		t,
		func() bool {
			response := Get(t, url)

			if response.Status != http.StatusOK {
				return false
			}

			status := Decode[contracts.ArchiveStatus](t, response)

			if status.Capture.Captured < lastCaptured {
				progression.CaptureIncreased = false
			}

			lastCaptured = status.Capture.Captured

			lastObserved := progression.Observed[len(progression.Observed)-1]
			if lastObserved != status.Status {
				progression.Observed = append(progression.Observed, status.Status)
			}

			switch status.Status {
			case "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "COMPENSATED":
				progression.Final = status

				return true
			default:
				return false
			}
		},
		timeout,
		100*time.Millisecond,
		"archive did not reach a terminal state",
	)

	for index := 1; index < len(progression.Observed); index++ {
		if statusRanks[progression.Observed[index-1]] > statusRanks[progression.Observed[index]] {
			progression.Ordered = false
		}
	}

	return progression
}

func RequireDistinctCapturedPages(
	t *testing.T,
	pages []contracts.PageOutcome,
) {
	t.Helper()

	seenURLs := make(map[string]bool)
	seenSnapshotIDs := make(map[string]bool)

	for _, page := range pages {
		require.False(t, seenURLs[page.URL], "duplicate page URL: %s", page.URL)

		require.Equal(t, "CAPTURED", page.Status)

		require.False(
			t,
			seenSnapshotIDs[page.SnapshotID],
		)

		seenURLs[page.URL] = true
		seenSnapshotIDs[page.SnapshotID] = true
	}
}
