package main

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/services/gateway/internal/testutil"
	"github.com/stretchr/testify/require"
)

func startGateway(t *testing.T, upstreams testutil.Upstreams) string {
	server := NewGatewayServer(
		Config{
			coordinatorURL:  upstreams.Coordinator.URL,
			captureURL:      upstreams.Capture.URL,
			loginURL:        upstreams.Login.URL,
			searchURL:       upstreams.Search.URL,
			upstreamTimeout: time.Second,
			streamTimeout:   time.Second,
			shutdownTimeout: time.Second,
		},
		testutil.Logger(),
	)
	ctx, cancel := context.WithCancel(context.Background())

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)

	stopped := make(chan error, 1)

	go func() {
		stopped <- server.Serve(ctx, listener)
	}()

	t.Cleanup(func() {
		cancel()

		require.NoError(t, <-stopped)
	})

	gateway := "http://" + listener.Addr().String()
	testutil.WaitUntilReady(t, gateway)

	return gateway
}
