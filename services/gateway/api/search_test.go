package api_test

import (
	"io"
	"net/http"
	"testing"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/gatewaytest"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/stretchr/testify/assert"
)

const searchResults = `{"results":[{"archiveId":"run-1","snapshotId":"snap-1","url":"https://example.org/","capturedAt":"2026-11-18T12:00:00Z","snippet":"archived text"}]}`

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
