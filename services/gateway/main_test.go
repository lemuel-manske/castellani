package main

import (
	"context"
	"net"
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGateway_ShutdownStopsServingAndClearsReadiness(t *testing.T) {
	gateway := startRunningGateway(t)

	response, err := (&http.Client{Timeout: time.Second}).Get(gateway.address + "/health/live")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusOK, response.StatusCode)

	gateway.stop()
	require.NoError(t, <-gateway.stopped)

	assert.False(t, gateway.server.ready.Load())
}

func TestGateway_DefaultConfigurationUsesBoundedTimeouts(t *testing.T) {
	cfg, err := configuredGateway(nil)
	require.NoError(t, err)

	assert.Equal(t, ":8080", cfg.address)
	assert.Equal(t, 10*time.Second, cfg.shutdownTimeout)
	assert.Equal(t, 5*time.Second, cfg.upstreamTimeout)
	assert.Equal(t, "http://coordinator:8080", cfg.coordinatorURL.String())
}

func TestGateway_MissingCoordinatorConfigurationFailsStartup(t *testing.T) {
	_, err := loadConfig(func(string) string { return "" })

	require.ErrorContains(t, err, "COORDINATOR_URL is required")
}

func TestGateway_CoordinatorCredentialsAreRejected(t *testing.T) {
	_, err := configuredGateway(map[string]string{
		"COORDINATOR_URL": "http://user:password@coordinator:8080",
	})

	require.ErrorContains(t, err, "COORDINATOR_URL")
}

func TestGateway_InvalidListenAddressIsRejected(t *testing.T) {
	_, err := configuredGateway(map[string]string{
		"GATEWAY_ADDR": "not-an-address",
	})

	require.ErrorContains(t, err, "GATEWAY_ADDR")
}

func TestGateway_ZeroShutdownTimeoutIsRejected(t *testing.T) {
	_, err := configuredGateway(map[string]string{
		"GATEWAY_SHUTDOWN_TIMEOUT": "0s",
	})

	require.ErrorContains(t, err, "must be positive")
}

func TestGateway_InvalidShutdownDurationIsRejected(t *testing.T) {
	_, err := configuredGateway(map[string]string{
		"GATEWAY_SHUTDOWN_TIMEOUT": "soon",
	})

	require.ErrorContains(t, err, "GATEWAY_SHUTDOWN_TIMEOUT")
}

func TestGateway_ExplicitConfigurationOverridesDefaults(t *testing.T) {
	cfg, err := configuredGateway(map[string]string{
		"GATEWAY_ADDR":             "127.0.0.1:9090",
		"GATEWAY_SHUTDOWN_TIMEOUT": "3s",
		"GATEWAY_UPSTREAM_TIMEOUT": "2s",
		"COORDINATOR_URL":          "https://coordinator.internal:8443",
	})
	require.NoError(t, err)

	assert.Equal(t, "127.0.0.1:9090", cfg.address)
	assert.Equal(t, 3*time.Second, cfg.shutdownTimeout)
	assert.Equal(t, 2*time.Second, cfg.upstreamTimeout)
	assert.Equal(t, "https://coordinator.internal:8443", cfg.coordinatorURL.String())
}
