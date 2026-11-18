package api_test

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/lemuel-manske/unnamed/services/gateway/api"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/coordinator"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const validSubmission = `{"seedUrl":"https://example.org/","maxDepth":0,"maxPages":1}`

func startGateway(t *testing.T, upstream http.HandlerFunc) *httptest.Server {
	t.Helper()
	coordinatorServer := httptest.NewServer(upstream)
	t.Cleanup(coordinatorServer.Close)

	origin, err := url.Parse(coordinatorServer.URL)
	require.NoError(t, err)

	app := application.NewApplication(coordinator.NewClient(*origin, time.Second))
	gateway := httptest.NewServer(api.NewRouter(func() bool { return true }, app, slog.Default()))
	t.Cleanup(gateway.Close)
	return gateway
}

func submit(t *testing.T, gateway *httptest.Server, key, body string) *http.Response {
	t.Helper()
	request, err := http.NewRequest(http.MethodPost, gateway.URL+"/archives", strings.NewReader(body))
	require.NoError(t, err)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", key)

	response, err := gateway.Client().Do(request)
	require.NoError(t, err)
	t.Cleanup(func() { _ = response.Body.Close() })
	return response
}

func TestGateway_ArchiveAdmissionForwardsIdempotencyAndReturnsStatusLocation(t *testing.T) {
	requests := make(chan string, 1)
	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		requests <- r.Header.Get("Idempotency-Key")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = io.WriteString(w, `{"archiveId":"run-1","status":"ACCEPTED","statusUrl":"/internal/run-1"}`)
	})

	response := submit(t, gateway, "sample-key-123", validSubmission)
	data, err := io.ReadAll(response.Body)
	require.NoError(t, err)

	assert.Equal(t, http.StatusAccepted, response.StatusCode)
	assert.Equal(t, "/archives/run-1", response.Header.Get("Location"))
	assert.JSONEq(t, `{"archiveId":"run-1","status":"ACCEPTED","statusUrl":"/archives/run-1"}`, string(data))
	assert.Equal(t, "sample-key-123", <-requests)
}

func TestGateway_ArchiveStatusReadsCoordinatorState(t *testing.T) {
	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/archives/run-1", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"archiveId":"run-1","status":"RUNNING","capture":{"captured":0,"failed":0,"pending":1},"replay":{"status":"NOT_READY"},"search":{"status":"PENDING"}}`)
	})

	response, err := gateway.Client().Get(gateway.URL + "/archives/run-1")
	require.NoError(t, err)
	defer response.Body.Close()

	var result struct{ Status string `json:"status"` }
	require.NoError(t, json.NewDecoder(response.Body).Decode(&result))

	assert.Equal(t, http.StatusOK, response.StatusCode)
	assert.Equal(t, "RUNNING", result.Status)
}

func TestGateway_SameIdempotencyKeyCanBeRetriedWithoutGatewayState(t *testing.T) {
	var forwarded atomic.Int32
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		forwarded.Add(1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = io.WriteString(w, `{"archiveId":"run-1","status":"ACCEPTED","statusUrl":"/archives/run-1"}`)
	})

	first := submit(t, gateway, "repeated-key-123", validSubmission)
	second := submit(t, gateway, "repeated-key-123", validSubmission)

	assert.Equal(t, http.StatusAccepted, first.StatusCode)
	assert.Equal(t, http.StatusAccepted, second.StatusCode)
	assert.EqualValues(t, 2, forwarded.Load())
}

func TestGateway_ArchiveAdmissionPreservesConflict(t *testing.T) {
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/problem+json")
		w.WriteHeader(http.StatusConflict)
		_, _ = io.WriteString(w, `{"type":"urn:coordinator:idempotency-conflict","title":"Conflict","status":409,"detail":"Key was used for different content."}`)
	})

	response := submit(t, gateway, "repeated-key-123", validSubmission)
	var result struct{ Type string `json:"type"` }
	require.NoError(t, json.NewDecoder(response.Body).Decode(&result))

	assert.Equal(t, http.StatusConflict, response.StatusCode)
	assert.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))
	assert.Equal(t, "urn:coordinator:idempotency-conflict", result.Type)
}

func TestGateway_MissingIdempotencyKeyNeverReachesCoordinator(t *testing.T) {
	var forwarded atomic.Int32
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		forwarded.Add(1)
		w.WriteHeader(http.StatusAccepted)
	})

	response := submit(t, gateway, "", validSubmission)

	assert.Equal(t, http.StatusBadRequest, response.StatusCode)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_ArchiveAdmissionRejectsUnknownFields(t *testing.T) {
	var forwarded atomic.Int32
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		forwarded.Add(1)
		w.WriteHeader(http.StatusAccepted)
	})

	response := submit(t, gateway, "sample-key-123", `{"seedUrl":"https://example.org/","maxDepth":0,"maxPages":1,"unsupported":true}`)

	assert.Equal(t, http.StatusBadRequest, response.StatusCode)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_ArchiveAdmissionRejectsInvalidLimits(t *testing.T) {
	var forwarded atomic.Int32
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		forwarded.Add(1)
		w.WriteHeader(http.StatusAccepted)
	})

	response := submit(t, gateway, "sample-key-123", `{"seedUrl":"https://example.org/","maxDepth":-1,"maxPages":0}`)

	assert.Equal(t, http.StatusUnprocessableEntity, response.StatusCode)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_ArchiveAdmissionRejectsOversizedBody(t *testing.T) {
	var forwarded atomic.Int32
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		forwarded.Add(1)
		w.WriteHeader(http.StatusAccepted)
	})

	response := submit(t, gateway, "sample-key-123", validSubmission+strings.Repeat(" ", 70<<10))

	assert.Equal(t, http.StatusBadRequest, response.StatusCode)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_ArchiveAdmissionReturnsUnavailableWhenCoordinatorDisconnects(t *testing.T) {
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		panic(http.ErrAbortHandler)
	})

	response := submit(t, gateway, "sample-key-123", validSubmission)

	assert.Equal(t, http.StatusServiceUnavailable, response.StatusCode)
	assert.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))
}

func TestGateway_ArchiveAdmissionDoesNotAcceptMalformedCoordinatorResponse(t *testing.T) {
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusAccepted)
		_, _ = io.WriteString(w, `{"archiveId":"","status":"ACCEPTED"}`)
	})

	response := submit(t, gateway, "sample-key-123", validSubmission)

	assert.Equal(t, http.StatusBadGateway, response.StatusCode)
}

func TestGateway_StatusRejectsUnexpectedCoordinatorDocument(t *testing.T) {
	gateway := startGateway(t, func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, `{"archiveId":"different-run","status":"RUNNING","capture":{},"replay":{},"search":{}}`)
	})

	response, err := gateway.Client().Get(gateway.URL + "/archives/run-1")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusBadGateway, response.StatusCode)
}

func TestGateway_UnknownRouteReturnsProblemDetails(t *testing.T) {
	gateway := startGateway(t, func(http.ResponseWriter, *http.Request) {})

	response, err := gateway.Client().Get(gateway.URL + "/unknown")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusNotFound, response.StatusCode)
	assert.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))
	assert.NotEmpty(t, response.Header.Get("X-Request-ID"))
}

func TestGateway_UnsupportedMethodReturnsProblemDetails(t *testing.T) {
	gateway := startGateway(t, func(http.ResponseWriter, *http.Request) {})
	request, err := http.NewRequest(http.MethodPut, gateway.URL+"/archives/run-1", nil)
	require.NoError(t, err)

	response, err := gateway.Client().Do(request)
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusMethodNotAllowed, response.StatusCode)
	assert.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))
}
