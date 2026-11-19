package main

import (
	"context"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"testing"
	"time"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/gatewaytest"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGateway_ShutdownStopsServingAndClearsReadiness(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	t.Cleanup(func() { _ = listener.Close() })

	coordinatorURL, err := url.Parse(gatewaytest.CoordinatorURL)
	require.NoError(t, err)

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	server := newGatewayServer(config{
		shutdownTimeout: time.Second,
		upstreamTimeout: time.Second,
		coordinatorURL:  coordinatorURL,
	}, logger)

	ctx, stop := context.WithCancel(context.Background())
	t.Cleanup(stop)

	stopped := make(chan error, 1)
	go func() {
		stopped <- server.serve(ctx, listener)
	}()

	require.Eventually(t, server.ready.Load, time.Second, time.Millisecond)

	client := &http.Client{Timeout: time.Second}
	response, err := client.Get("http://" + listener.Addr().String() + "/health/live")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusOK, response.StatusCode)

	stop()
	require.NoError(t, <-stopped)

	assert.False(t, server.ready.Load())
}

func TestGateway_DefaultConfigurationUsesBoundedTimeouts(t *testing.T) {
	cfg, err := loadConfig(gatewaytest.Environment(nil))
	require.NoError(t, err)

	assert.Equal(t, ":8080", cfg.address)
	assert.Equal(t, 10*time.Second, cfg.shutdownTimeout)
	assert.Equal(t, 5*time.Second, cfg.upstreamTimeout)
	assert.Equal(t, gatewaytest.CoordinatorURL, cfg.coordinatorURL.String())
}

func TestGateway_MissingCoordinatorConfigurationFailsStartup(t *testing.T) {
	_, err := loadConfig(func(string) string { return "" })

	require.ErrorContains(t, err, "COORDINATOR_URL is required")
}

func TestGateway_CoordinatorCredentialsAreRejected(t *testing.T) {
	settings := map[string]string{
		"COORDINATOR_URL": "http://user:password@coordinator:8080",
	}

	_, err := loadConfig(gatewaytest.Environment(settings))

	require.ErrorContains(t, err, "COORDINATOR_URL")
}

func TestGateway_InvalidListenAddressIsRejected(t *testing.T) {
	settings := map[string]string{
		"GATEWAY_ADDR": "not-an-address",
	}

	_, err := loadConfig(gatewaytest.Environment(settings))

	require.ErrorContains(t, err, "GATEWAY_ADDR")
}

func TestGateway_ZeroShutdownTimeoutIsRejected(t *testing.T) {
	settings := map[string]string{
		"GATEWAY_SHUTDOWN_TIMEOUT": "0s",
	}

	_, err := loadConfig(gatewaytest.Environment(settings))

	require.ErrorContains(t, err, "must be positive")
}

func TestGateway_InvalidShutdownDurationIsRejected(t *testing.T) {
	settings := map[string]string{
		"GATEWAY_SHUTDOWN_TIMEOUT": "soon",
	}

	_, err := loadConfig(gatewaytest.Environment(settings))

	require.ErrorContains(t, err, "GATEWAY_SHUTDOWN_TIMEOUT")
}

func TestGateway_ExplicitConfigurationOverridesDefaults(t *testing.T) {
	settings := map[string]string{
		"GATEWAY_ADDR":             "127.0.0.1:9090",
		"GATEWAY_SHUTDOWN_TIMEOUT": "3s",
		"GATEWAY_UPSTREAM_TIMEOUT": "2s",
		"COORDINATOR_URL":          "https://coordinator.internal:8443",
	}

	cfg, err := loadConfig(gatewaytest.Environment(settings))
	require.NoError(t, err)

	assert.Equal(t, "127.0.0.1:9090", cfg.address)
	assert.Equal(t, 3*time.Second, cfg.shutdownTimeout)
	assert.Equal(t, 2*time.Second, cfg.upstreamTimeout)
	assert.Equal(t, "https://coordinator.internal:8443", cfg.coordinatorURL.String())
}
