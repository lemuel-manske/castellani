//go:build integration

package main

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"testing"
	"time"

	archiveapi "github.com/lemuel-manske/castellani/services/coordinator/api/archive"
	"github.com/lemuel-manske/castellani/services/coordinator/assembly"
	"github.com/lemuel-manske/castellani/services/coordinator/internal/testutil"
	"github.com/stretchr/testify/require"
)

func startCoordinator(t *testing.T) string {
	t.Helper()

	serviceConfig, err := LoadConfig(os.Getenv)
	require.NoError(t, err)

	built, err := assembly.NewCoordinatorContext(
		context.Background(),
		serviceConfig.region,
		serviceConfig.awsAccessKeyID,
		serviceConfig.awsSecretAccessKey,
		serviceConfig.dynamoEndpoint,
		serviceConfig.rabbitURL,
	)
	require.NoError(t, err)

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)

	ctx, cancel := context.WithCancel(context.Background())
	server := NewCoordinatorServer(
		serviceConfig,
		built.Application,
		testutil.Logger(),
	)
	stopped := make(chan error, 1)

	go func() {
		stopped <- server.Serve(ctx, listener)
	}()

	StartDispatchWorker(
		ctx,
		testutil.Logger(),
		built.Dispatcher,
	)
	StartEventConsumerWorker(
		ctx,
		testutil.Logger(),
		built.Application,
		built.Consumer,
	)

	t.Cleanup(func() {
		cancel()
		require.NoError(t, <-stopped)
	})

	coordinatorURL := "http://" + listener.Addr().String()
	testutil.WaitUntilReady(t, coordinatorURL)

	return coordinatorURL
}

func waitForArchiveStatus(
	t *testing.T,
	coordinatorURL, statusURL, expectedStatus string,
) archiveapi.ArchiveResponse {
	t.Helper()

	var status archiveapi.ArchiveResponse

	require.Eventually(
		t,
		func() bool {
			response, err := http.Get(coordinatorURL + statusURL)

			if err != nil {
				return false
			}

			defer response.Body.Close()

			if response.StatusCode != http.StatusOK {
				return false
			}

			body, err := io.ReadAll(response.Body)

			if err != nil {
				return false
			}

			if err = json.Unmarshal(body, &status); err != nil {
				return false
			}

			return status.Status == expectedStatus
		},
		5*time.Second,
		10*time.Millisecond,
	)

	return status
}
