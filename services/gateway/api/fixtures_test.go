package api_test

import (
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/lemuel-manske/unnamed/services/gateway/api"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/coordinator"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/stretchr/testify/require"
)

const (
	archiveID       = "run-1"
	idempotencyKey  = "sample-key-123"
	validSubmission = `{"seedUrl":"https://example.org/","maxDepth":0,"maxPages":1}`
	acceptedArchive = `{"archiveId":"run-1","status":"ACCEPTED","statusUrl":"/internal/run-1"}`
	runningArchive  = `{"archiveId":"run-1","status":"RUNNING","capture":{"captured":0,"failed":0,"pending":1},"replay":{"status":"NOT_READY"},"search":{"status":"PENDING"}}`
)

type response struct {
	Status int
	Header http.Header
	Body   string
}

type gatewayFixture struct {
	t      *testing.T
	server *httptest.Server
}

func startGateway(t *testing.T, coordinatorHandler http.HandlerFunc) gatewayFixture {
	t.Helper()

	upstream := httptest.NewServer(coordinatorHandler)
	t.Cleanup(upstream.Close)

	origin, err := url.Parse(upstream.URL)
	require.NoError(t, err)

	client := coordinator.NewClient(*origin, time.Second)
	app := application.NewApplication(client)
	gateway := httptest.NewServer(api.NewRouter(func() bool { return true }, app, slog.Default()))
	t.Cleanup(gateway.Close)

	return gatewayFixture{t: t, server: gateway}
}

func startUnreadyGateway(t *testing.T) gatewayFixture {
	t.Helper()

	router := api.NewRouter(func() bool { return false }, application.Application{}, slog.Default())
	server := httptest.NewServer(router)
	t.Cleanup(server.Close)

	return gatewayFixture{t: t, server: server}
}

func (g gatewayFixture) submit(key, body string) response {
	g.t.Helper()

	request, err := http.NewRequest(http.MethodPost, g.server.URL+httpx.ArchivesPath, strings.NewReader(body))
	require.NoError(g.t, err)

	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	request.Header.Set(httpx.IdempotencyHeader, key)

	return g.send(request)
}

func (g gatewayFixture) get(path string) response {
	g.t.Helper()

	request, err := http.NewRequest(http.MethodGet, g.server.URL+path, nil)
	require.NoError(g.t, err)

	return g.send(request)
}

func (g gatewayFixture) put(path string) response {
	g.t.Helper()

	request, err := http.NewRequest(http.MethodPut, g.server.URL+path, nil)
	require.NoError(g.t, err)

	return g.send(request)
}

func (g gatewayFixture) send(request *http.Request) response {
	g.t.Helper()

	result, err := g.server.Client().Do(request)
	require.NoError(g.t, err)
	defer result.Body.Close()

	body, err := io.ReadAll(result.Body)
	require.NoError(g.t, err)

	return response{
		Status: result.StatusCode,
		Header: result.Header.Clone(),
		Body:   string(body),
	}
}

func coordinatorAcceptsArchive(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	w.WriteHeader(http.StatusAccepted)
	_, _ = io.WriteString(w, acceptedArchive)
}

func coordinatorReturnsArchiveStatus(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	_, _ = io.WriteString(w, runningArchive)
}

func coordinatorRejectsConflictingKey(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeProblem)
	w.WriteHeader(http.StatusConflict)
	_, _ = io.WriteString(w, `{"type":"urn:coordinator:idempotency-conflict","title":"Conflict","status":409,"detail":"Key was used for different content."}`)
}

func coordinatorDisconnects(http.ResponseWriter, *http.Request) {
	panic(http.ErrAbortHandler)
}

func coordinatorReturnsMalformedAdmission(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusAccepted)
	_, _ = io.WriteString(w, `{"archiveId":"","status":"ACCEPTED"}`)
}

func coordinatorReturnsMismatchedArchive(w http.ResponseWriter, _ *http.Request) {
	_, _ = io.WriteString(w, `{"archiveId":"different-run","status":"RUNNING","capture":{},"replay":{},"search":{}}`)
}

func coordinatorIsUnused(http.ResponseWriter, *http.Request) {}
