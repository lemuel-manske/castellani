package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGateway_LivenessEndpointReturnsOK(t *testing.T) {
	server := httptest.NewServer(newHandler())
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

func TestGateway_ReadinessEndpointReturnsOK(t *testing.T) {
	server := httptest.NewServer(newHandler())
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/health/ready")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusOK, response.StatusCode)
}

func TestGateway_UnknownRouteIsNotFound(t *testing.T) {
	server := httptest.NewServer(newHandler())
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/archives")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusNotFound, response.StatusCode)
}

func TestGateway_HealthEndpointRejectsUnsupportedMethod(t *testing.T) {
	server := httptest.NewServer(newHandler())
	t.Cleanup(server.Close)

	request, err := http.NewRequest(http.MethodPost, server.URL+"/health/live", nil)
	require.NoError(t, err)

	response, err := server.Client().Do(request)
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusMethodNotAllowed, response.StatusCode)
}
