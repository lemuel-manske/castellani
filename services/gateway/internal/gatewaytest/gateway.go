// Package gatewaytest provides HTTP fixtures for testing the Gateway's public behavior.
package gatewaytest

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
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
	"github.com/stretchr/testify/require"
)

const (
	ArchiveID        = "run-1"
	IdempotencyKey   = "sample-key-123"
	ValidSubmission  = `{"seedUrl":"https://example.org/","maxDepth":0,"maxPages":1}`
	AcceptedArchive  = `{"archiveId":"run-1","status":"ACCEPTED","statusUrl":"/internal/run-1"}`
	RunningArchive   = `{"archiveId":"run-1","status":"RUNNING","capture":{"captured":0,"failed":0,"pending":1},"replay":{"status":"NOT_READY"},"search":{"status":"PENDING"}}`
)

type Response struct {
	Status int
	Header http.Header
	Body   string
}

type Gateway struct {
	t      *testing.T
	server *httptest.Server
}

func Start(t *testing.T, coordinatorHandler http.HandlerFunc) Gateway {
	t.Helper()

	upstream := httptest.NewServer(coordinatorHandler)
	t.Cleanup(upstream.Close)

	origin, err := url.Parse(upstream.URL)
	require.NoError(t, err)

	client := coordinator.NewHTTPClient(*origin, time.Second)
	app := application.NewApplication(client)
	router := api.NewRouter(func() bool { return true }, app, slog.Default())

	return start(t, router)
}

func StartWithServices(
	t *testing.T,
	coordinatorHandler http.HandlerFunc,
	captureHandler http.HandlerFunc,
	searchHandler http.HandlerFunc,
) Gateway {
	t.Helper()

	coordinatorServer := httptest.NewServer(coordinatorHandler)
	captureServer := httptest.NewServer(captureHandler)
	searchServer := httptest.NewServer(searchHandler)

	t.Cleanup(coordinatorServer.Close)
	t.Cleanup(captureServer.Close)
	t.Cleanup(searchServer.Close)

	coordinatorOrigin, err := url.Parse(coordinatorServer.URL)
	require.NoError(t, err)

	captureOrigin, err := url.Parse(captureServer.URL)
	require.NoError(t, err)

	searchOrigin, err := url.Parse(searchServer.URL)
	require.NoError(t, err)

	app := application.NewApplication(coordinator.NewHTTPClient(*coordinatorOrigin, time.Second))
	captureClient := upstream.NewClient(*captureOrigin, time.Second)
	searchClient := upstream.NewClient(*searchOrigin, time.Second)
	router := api.NewRouterWithServices(func() bool { return true }, app, captureClient, searchClient, slog.Default())

	return start(t, router)
}

func StartUnready(t *testing.T) Gateway {
	t.Helper()

	router := api.NewRouter(func() bool { return false }, application.Application{}, slog.Default())

	return start(t, router)
}

func start(t *testing.T, handler http.Handler) Gateway {
	t.Helper()

	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)

	return Gateway{t: t, server: server}
}

func (g Gateway) Submit(key, body string) Response {
	g.t.Helper()

	request, err := http.NewRequest(http.MethodPost, g.server.URL+httpx.ArchivesPath, strings.NewReader(body))
	require.NoError(g.t, err)

	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	request.Header.Set(httpx.IdempotencyHeader, key)

	return g.send(request)
}

func (g Gateway) CreateSession(key, body string) Response {
	g.t.Helper()

	request, err := http.NewRequest(http.MethodPost, g.server.URL+"/sessions", strings.NewReader(body))
	require.NoError(g.t, err)

	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	request.Header.Set(httpx.IdempotencyHeader, key)

	return g.send(request)
}

func (g Gateway) UpdateSession(id, body string) Response {
	g.t.Helper()

	request, err := http.NewRequest(http.MethodPut, g.server.URL+"/sessions/"+id, strings.NewReader(body))
	require.NoError(g.t, err)

	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)

	return g.send(request)
}

func (g Gateway) WACZ(id, byteRange, ifRange string) Response {
	g.t.Helper()

	request, err := http.NewRequest(http.MethodGet, g.server.URL+"/archives/"+id+"/wacz", nil)
	require.NoError(g.t, err)

	if byteRange != "" {
		request.Header.Set("Range", byteRange)
	}

	if ifRange != "" {
		request.Header.Set("If-Range", ifRange)
	}

	return g.send(request)
}

func (g Gateway) Head(path string) Response {
	g.t.Helper()

	return g.request(http.MethodHead, path)
}

func (g Gateway) Get(path string) Response {
	g.t.Helper()

	return g.request(http.MethodGet, path)
}

func (g Gateway) Put(path string) Response {
	g.t.Helper()

	return g.request(http.MethodPut, path)
}

func (g Gateway) request(method, path string) Response {
	g.t.Helper()

	request, err := http.NewRequest(method, g.server.URL+path, nil)
	require.NoError(g.t, err)

	return g.send(request)
}

func (g Gateway) send(request *http.Request) Response {
	g.t.Helper()

	response, err := g.server.Client().Do(request)
	require.NoError(g.t, err)
	defer response.Body.Close()

	body, err := io.ReadAll(response.Body)
	require.NoError(g.t, err)

	return Response{
		Status: response.StatusCode,
		Header: response.Header.Clone(),
		Body:   string(body),
	}
}
