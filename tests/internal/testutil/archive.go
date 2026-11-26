package testutil

import (
	"net/http"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
	"github.com/stretchr/testify/require"
)

func WaitForArchiveTerminalState(
	t *testing.T,
	baseURL string,
	statusURL string,
	timeout time.Duration,
) contracts.ArchiveStatus {
	t.Helper()

	var (
		status       contracts.ArchiveStatus
		lastResponse Result
	)

	require.Eventually(
		t,
		func() bool {
			lastResponse = Get(t, baseURL, statusURL)
			if lastResponse.Status != http.StatusOK {
				return false
			}

			status = Decode[contracts.ArchiveStatus](t, lastResponse)

			switch status.Status {
			case "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED":
				return true
			default:
				return false
			}
		},
		timeout,
		500*time.Millisecond,
		"archive did not reach a terminal state; last response: %s",
		lastResponse.Body,
	)

	return status
}
