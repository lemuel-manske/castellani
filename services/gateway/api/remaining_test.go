package api_test

import (
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/gatewaytest"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/stretchr/testify/assert"
)

const (
	sessionRequest = `{"archiveId":"run-1","targetUrl":"https://example.org/login"}`
	sessionCreated = `{"sessionId":"sess-1","archiveId":"run-1","status":"CREATED","expiresAt":"2026-11-18T23:00:00Z"}`
	searchResults  = `{"results":[{"archiveId":"run-1","snapshotId":"snap-1","url":"https://example.org/","capturedAt":"2026-11-18T12:00:00Z","snippet":"archived text"}]}`
)

func TestGateway_SearchReturnsHistoricalSnapshotsFromSearchService(t *testing.T) {
	receivedQuery := make(chan string, 1)

	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, gatewaytest.Unused, func(w http.ResponseWriter, r *http.Request) {
		receivedQuery <- r.URL.RawQuery
		w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
		_, _ = io.WriteString(w, searchResults)
	})

	result := gateway.Get("/search?q=historical&archiveId=run-1&limit=10")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.JSONEq(t, searchResults, result.Body)
	assert.Equal(t, "q=historical&archiveId=run-1&limit=10", <-receivedQuery)
}

func TestGateway_SearchWithoutQueryIsRejectedBeforeCallingSearchService(t *testing.T) {
	coordinator := &gatewaytest.RecordingCoordinator{}
	gateway := gatewaytest.StartWithServices(t, coordinator.Accept, gatewaytest.Unused, gatewaytest.Unused)

	result := gateway.Get("/search?limit=10")

	assert.Equal(t, http.StatusBadRequest, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
}

func TestGateway_SearchWithInvalidLimitReturnsValidationError(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, gatewaytest.Unused, gatewaytest.Unused)

	result := gateway.Get("/search?q=archive&limit=101")

	assert.Equal(t, http.StatusBadRequest, result.Status)
}

func TestGateway_SearchOutageDoesNotDisableLiveness(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, gatewaytest.Unused, gatewaytest.Disconnect)

	search := gateway.Get("/search?q=archive")
	health := gateway.Get("/health/live")

	assert.Equal(t, http.StatusServiceUnavailable, search.Status)
	assert.Equal(t, http.StatusOK, health.Status)
}

func TestGateway_CreateSessionRetainsIdempotencyKeyAndPublicLocation(t *testing.T) {
	keys := make(chan string, 1)
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, r *http.Request) {
		keys <- r.Header.Get(httpx.IdempotencyHeader)
		w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
		w.Header().Set(httpx.LocationHeader, "http://capture.internal/private/sess-1")
		w.WriteHeader(http.StatusCreated)
		_, _ = io.WriteString(w, sessionCreated)
	}, gatewaytest.Unused)

	result := gateway.CreateSession(gatewaytest.IdempotencyKey, sessionRequest)

	assert.Equal(t, http.StatusCreated, result.Status)
	assert.JSONEq(t, sessionCreated, result.Body)
	assert.Equal(t, "/sessions/sess-1", result.Header.Get(httpx.LocationHeader))
	assert.Equal(t, gatewaytest.IdempotencyKey, <-keys)
}

func TestGateway_CreateSessionWithoutIdempotencyKeyIsRejected(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, gatewaytest.Unused, gatewaytest.Unused)

	result := gateway.CreateSession("", sessionRequest)

	assert.Equal(t, http.StatusBadRequest, result.Status)
}

func TestGateway_CreateSessionRejectsNonHTTPSTarget(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, gatewaytest.Unused, gatewaytest.Unused)

	result := gateway.CreateSession(gatewaytest.IdempotencyKey, `{"archiveId":"run-1","targetUrl":"file:///etc/passwd"}`)

	assert.Equal(t, http.StatusBadRequest, result.Status)
}

func TestGateway_SessionFinalizationForwardsDesiredState(t *testing.T) {
	received := make(chan string, 1)
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		received <- string(body)
		w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
		_, _ = io.WriteString(w, `{"sessionId":"sess-1","archiveId":"run-1","status":"COMPLETED","expiresAt":"2026-11-18T23:00:00Z","authGeneration":1}`)
	}, gatewaytest.Unused)

	result := gateway.UpdateSession("sess-1", `{"status":"COMPLETED"}`)

	assert.Equal(t, http.StatusOK, result.Status)
	assert.JSONEq(t, `{"status":"COMPLETED"}`, <-received)
	assert.Contains(t, result.Body, `"authGeneration":1`)
}

func TestGateway_SessionFinalizationRejectsInvalidTransition(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, gatewaytest.Unused, gatewaytest.Unused)

	result := gateway.UpdateSession("sess-1", `{"status":"ACTIVE"}`)

	assert.Equal(t, http.StatusBadRequest, result.Status)
}

func TestGateway_PageListingReturnsCapturedOutcomes(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
		_, _ = io.WriteString(w, `{"items":[{"url":"https://example.org/","status":"CAPTURED","snapshotId":"snap-1"}]}`)
	}, gatewaytest.Unused)

	result := gateway.Get("/archives/run-1/pages?limit=10")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Contains(t, result.Body, `"snapshotId":"snap-1"`)
}

func TestGateway_SnapshotResolutionReturnsCommittedMetadata(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
		_, _ = io.WriteString(w, `{"archiveId":"run-1","snapshotId":"snap-1","url":"https://example.org/","capturedAt":"2026-11-18T12:00:00Z"}`)
	}, gatewaytest.Unused)

	result := gateway.Get("/archives/run-1/snapshots/snap-1")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Contains(t, result.Body, `"snapshotId":"snap-1"`)
}

func TestGateway_PublishedWACZStreamsBytesWithoutRewriting(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Accept-Ranges", "bytes")
		w.Header().Set("ETag", `"digest-1"`)
		_, _ = io.WriteString(w, "WACZ-PAYLOAD")
	}, gatewaytest.Unused)

	result := gateway.WACZ("run-1", "", "")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Equal(t, "WACZ-PAYLOAD", result.Body)
	assert.Equal(t, "bytes", result.Header.Get("Accept-Ranges"))
	assert.Equal(t, `"digest-1"`, result.Header.Get("ETag"))
}

func TestGateway_WACZRangeRequestPreservesPartialContentSemantics(t *testing.T) {
	receivedRange := make(chan string, 1)
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, r *http.Request) {
		receivedRange <- r.Header.Get("Range")
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Accept-Ranges", "bytes")
		w.Header().Set("Content-Range", "bytes 0-3/8")
		w.WriteHeader(http.StatusPartialContent)
		_, _ = io.WriteString(w, "WACZ")
	}, gatewaytest.Unused)

	result := gateway.WACZ("run-1", "bytes=0-3", "")

	assert.Equal(t, http.StatusPartialContent, result.Status)
	assert.Equal(t, "bytes=0-3", <-receivedRange)
	assert.Equal(t, "bytes 0-3/8", result.Header.Get("Content-Range"))
	assert.Equal(t, "WACZ", result.Body)
}

func TestGateway_WACZHeadReturnsMetadataWithoutReadingBytes(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Content-Length", "900")
		w.Header().Set("ETag", `"digest-1"`)
		w.WriteHeader(http.StatusOK)
	}, gatewaytest.Unused)

	result := gateway.Head("/archives/run-1/wacz")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Empty(t, result.Body)
	assert.Equal(t, "900", result.Header.Get("Content-Length"))
}

func TestGateway_UnpublishedWACZIsNotExposed(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeProblem)
		w.WriteHeader(http.StatusNotFound)
		_, _ = io.WriteString(w, `{"type":"urn:capture:unpublished","title":"Not Found","status":404}`)
	}, gatewaytest.Unused)

	result := gateway.WACZ("run-1", "", "")

	assert.Equal(t, http.StatusNotFound, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
	assert.NotContains(t, strings.ToLower(result.Body), "s3://")
}

func TestGateway_WACZUnsatisfiableRangePreservesContentRange(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeProblem)
		w.Header().Set("Content-Range", "bytes */8")
		w.WriteHeader(http.StatusRequestedRangeNotSatisfiable)
		_, _ = io.WriteString(w, `{"type":"urn:capture:range","title":"Range Not Satisfiable","status":416}`)
	}, gatewaytest.Unused)

	result := gateway.WACZ("run-1", "bytes=900-1000", "")

	assert.Equal(t, http.StatusRequestedRangeNotSatisfiable, result.Status)
	assert.Equal(t, "bytes */8", result.Header.Get("Content-Range"))
}

func TestGateway_MultipleWACZRangesAreRejectedBeforeCapture(t *testing.T) {
	gateway := gatewaytest.StartWithServices(t, gatewaytest.Unused, gatewaytest.Unused, gatewaytest.Unused)

	result := gateway.WACZ("run-1", "bytes=0-1,3-4", "")

	assert.Equal(t, http.StatusBadRequest, result.Status)
}
