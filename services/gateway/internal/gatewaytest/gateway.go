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

type Option func(*serviceOptions)

type serviceOptions struct {
	coordinator http.HandlerFunc
	capture     http.HandlerFunc
	search      http.HandlerFunc
	ready       bool
}

func WithCoordinatorService(handler http.HandlerFunc) Option {
	return func(options *serviceOptions) {
		options.coordinator = handler
	}
}

func WithCaptureService(handler http.HandlerFunc) Option {
	return func(options *serviceOptions) {
		options.capture = handler
	}
}

func WithSearchService(handler http.HandlerFunc) Option {
	return func(options *serviceOptions) {
		options.search = handler
	}
}

func WithReadiness(ready bool) Option {
	return func(options *serviceOptions) {
		options.ready = ready
	}
}

func Start(t *testing.T, options ...Option) Gateway {
	t.Helper()

	services := serviceOptions{
		ready: true,
	}

	for _, option := range options {
		option(&services)
	}

	coordinatorOrigin := startService(t, "Coordinator", services.coordinator)
	captureOrigin := startService(t, "Capture", services.capture)
	searchOrigin := startService(t, "Search", services.search)

	coordinatorClient := coordinator.NewHTTPClient(coordinatorOrigin, time.Second)
	captureClient := upstream.NewClient(captureOrigin, time.Second)
	searchClient := upstream.NewClient(searchOrigin, time.Second)
	app := application.NewApplication(coordinatorClient)

	router := api.NewRouterWithServices(
		func() bool { return services.ready },
		app,
		captureClient,
		searchClient,
		slog.Default(),
	)

	server := httptest.NewServer(router)
	t.Cleanup(server.Close)

	return Gateway{t: t, server: server}
}

func startService(t *testing.T, name string, handler http.HandlerFunc) url.URL {
	t.Helper()

	if handler == nil {
		handler = func(w http.ResponseWriter, r *http.Request) {
			t.Errorf("unexpected %s service request: %s %s", name, r.Method, r.URL.RequestURI())
			http.Error(w, "unexpected test dependency call", http.StatusInternalServerError)
		}
	}

	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)

	origin, err := url.Parse(server.URL)
	require.NoError(t, err)

	return *origin
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
