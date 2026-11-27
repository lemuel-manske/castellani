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

	return Eventually(
		t,
		timeout,
		500*time.Millisecond,
		func() (contracts.ArchiveStatus, bool) {
			response := Get(t, baseURL, statusURL)
			if response.Status != http.StatusOK {
				return contracts.ArchiveStatus{}, false
			}

			status := Decode[contracts.ArchiveStatus](t, response)

			switch status.Status {
			case "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED":
				return status, true
			default:
				return contracts.ArchiveStatus{}, false
			}
		},
		"archive did not reach a terminal state",
	)
}
