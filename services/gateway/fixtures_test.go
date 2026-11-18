package main

import (
	"context"
	"net"
	"net/url"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type runningGateway struct {
	server  *gatewayServer
	address string
	stop    context.CancelFunc
	stopped <-chan error
}

func startRunningGateway(t *testing.T) runningGateway {
	t.Helper()

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)

	t.Cleanup(func() { _ = listener.Close() })

	coordinatorURL, err := url.Parse("http://127.0.0.1:9999")
	require.NoError(t, err)

	server := newGatewayServer(config{
		shutdownTimeout: time.Second,
		upstreamTimeout: time.Second,
		coordinatorURL:  coordinatorURL,
	}, nilLogger())

	ctx, stop := context.WithCancel(context.Background())
	t.Cleanup(stop)

	stopped := make(chan error, 1)
	go func() { stopped <- server.serve(ctx, listener) }()

	require.Eventually(t, server.ready.Load, time.Second, time.Millisecond)

	return runningGateway{
		server:  server,
		address: "http://" + listener.Addr().String(),
		stop:    stop,
		stopped: stopped,
	}
}

func configuredGateway(overrides map[string]string) (config, error) {
	settings := map[string]string{
		"COORDINATOR_URL": "http://coordinator:8080",
	}

	for name, value := range overrides {
		settings[name] = value
	}

	return loadConfig(func(name string) string {
		return settings[name]
	})
}
