package main

import (
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGateway_LivenessEndpointReturnsOK(t *testing.T) {
	server := httptest.NewServer(newHandler(func() bool { return false }))
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/health/live")
	require.NoError(t, err)
	defer response.Body.Close()

	body, err := io.ReadAll(response.Body)
	require.NoError(t, err)

	assert.Equal(t, http.StatusOK, response.StatusCode)
	assert.Equal(t, "text/plain; charset=utf-8", response.Header.Get("Content-Type"))
	assert.Equal(t, "ok\n", string(body))
}

func TestGateway_ReadinessEndpointReturnsOKWhenServing(t *testing.T) {
	server := httptest.NewServer(newHandler(func() bool { return true }))
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/health/ready")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusOK, response.StatusCode)
}

func TestGateway_ReadinessEndpointReturnsUnavailableBeforeServing(t *testing.T) {
	server := httptest.NewServer(newHandler(func() bool { return false }))
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/health/ready")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusServiceUnavailable, response.StatusCode)
}

func TestGateway_ShutdownStopsServingAndClearsReadiness(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	t.Cleanup(func() { _ = listener.Close() })

	gateway := newGatewayServer(config{shutdownTimeout: time.Second})
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	stopped := make(chan error, 1)
	go func() { stopped <- gateway.serve(ctx, listener) }()

	require.Eventually(t, gateway.ready.Load, time.Second, time.Millisecond)

	response, err := (&http.Client{Timeout: time.Second}).Get("http://" + listener.Addr().String() + "/health/live")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusOK, response.StatusCode)

	cancel()
	require.NoError(t, <-stopped)

	assert.False(t, gateway.ready.Load())
}

func TestGateway_UnknownRouteIsNotFound(t *testing.T) {
	server := httptest.NewServer(newHandler(func() bool { return true }))
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/archives")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusNotFound, response.StatusCode)
}

func TestGateway_HealthEndpointRejectsUnsupportedMethod(t *testing.T) {
	server := httptest.NewServer(newHandler(func() bool { return true }))
	t.Cleanup(server.Close)

	request, err := http.NewRequest(http.MethodPost, server.URL+"/health/live", nil)
	require.NoError(t, err)

	response, err := server.Client().Do(request)
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusMethodNotAllowed, response.StatusCode)
}

func TestGateway_ConfigUsesSafeDefaults(t *testing.T) {
	cfg, err := loadConfig(func(string) string { return "" })
	require.NoError(t, err)

	assert.Equal(t, ":8080", cfg.address)
	assert.Equal(t, 10*time.Second, cfg.shutdownTimeout)
}

func TestGateway_ConfigRejectsInvalidAddress(t *testing.T) {
	_, err := loadConfig(func(name string) string {
		return map[string]string{"GATEWAY_ADDR": "not-an-address"}[name]
	})

	require.ErrorContains(t, err, "GATEWAY_ADDR")
}

func TestGateway_ConfigRejectsNonPositiveShutdownTimeout(t *testing.T) {
	_, err := loadConfig(func(name string) string {
		return map[string]string{"GATEWAY_SHUTDOWN_TIMEOUT": "0s"}[name]
	})

	require.ErrorContains(t, err, "must be positive")
}

func TestGateway_ConfigRejectsInvalidShutdownTimeout(t *testing.T) {
	_, err := loadConfig(func(name string) string {
		return map[string]string{"GATEWAY_SHUTDOWN_TIMEOUT": "soon"}[name]
	})

	require.ErrorContains(t, err, "GATEWAY_SHUTDOWN_TIMEOUT")
}

func TestGateway_ConfigAcceptsExplicitValues(t *testing.T) {
	cfg, err := loadConfig(func(name string) string {
		switch name {
		case "GATEWAY_ADDR":
			return "127.0.0.1:9090"
		case "GATEWAY_SHUTDOWN_TIMEOUT":
			return "3s"
		default:
			return ""
		}
	})
	require.NoError(t, err)

	assert.Equal(t, "127.0.0.1:9090", cfg.address)
	assert.Equal(t, 3*time.Second, cfg.shutdownTimeout)
}

