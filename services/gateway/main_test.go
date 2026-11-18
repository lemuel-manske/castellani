package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGateway_LivenessEndpointReturnsOK(t *testing.T) {
	server := httptest.NewServer(newHandler())
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/health/live")
	if err != nil {
		t.Fatalf("request liveness: %v", err)
	}
	defer response.Body.Close()

	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatalf("read liveness response: %v", err)
	}

	if response.StatusCode != http.StatusOK {
		t.Errorf("status = %d; want %d", response.StatusCode, http.StatusOK)
	}
	if response.Header.Get("Content-Type") != "text/plain; charset=utf-8" {
		t.Errorf("content type = %q; want text/plain", response.Header.Get("Content-Type"))
	}
	if string(body) != "ok\n" {
		t.Errorf("body = %q; want %q", body, "ok\n")
	}
}

func TestGateway_ReadinessEndpointReturnsOK(t *testing.T) {
	server := httptest.NewServer(newHandler())
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/health/ready")
	if err != nil {
		t.Fatalf("request readiness: %v", err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Errorf("status = %d; want %d", response.StatusCode, http.StatusOK)
	}
}

func TestGateway_UnknownRouteIsNotFound(t *testing.T) {
	server := httptest.NewServer(newHandler())
	t.Cleanup(server.Close)

	response, err := server.Client().Get(server.URL + "/archives")
	if err != nil {
		t.Fatalf("request unimplemented route: %v", err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusNotFound {
		t.Errorf("status = %d; want %d", response.StatusCode, http.StatusNotFound)
	}
}

func TestGateway_HealthEndpointRejectsUnsupportedMethod(t *testing.T) {
	server := httptest.NewServer(newHandler())
	t.Cleanup(server.Close)

	request, err := http.NewRequest(http.MethodPost, server.URL+"/health/live", nil)
	if err != nil {
		t.Fatalf("construct request: %v", err)
	}

	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatalf("request liveness with POST: %v", err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("status = %d; want %d", response.StatusCode, http.StatusMethodNotAllowed)
	}
}
