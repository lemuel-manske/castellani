package api_test

import (
	"io"
	"net/http"
	"testing"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/gatewaytest"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/stretchr/testify/assert"
)

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
