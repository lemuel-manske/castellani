package api_test

import (
	"io"
	"net/http"
	"testing"

	sharedhttp "github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/gatewaytest"
	"github.com/stretchr/testify/assert"
)

func TestGateway_PageListingReturnsCapturedOutcomes(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(sharedhttp.HeaderContentType, sharedhttp.MediaTypeJSON)
		_, _ = io.WriteString(w, `{"items":[{"url":"https://example.org/","status":"CAPTURED","snapshotId":"snap-1"}]}`)
	}))

	result := gateway.Get("/archives/run-1/pages?limit=10")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Contains(t, result.Body, `"snapshotId":"snap-1"`)
}

func TestGateway_SnapshotResolutionReturnsCommittedMetadata(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(sharedhttp.HeaderContentType, sharedhttp.MediaTypeJSON)
		_, _ = io.WriteString(w, `{"archiveId":"run-1","snapshotId":"snap-1","url":"https://example.org/","capturedAt":"2026-11-18T12:00:00Z"}`)
	}))

	result := gateway.Get("/archives/run-1/snapshots/snap-1")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Contains(t, result.Body, `"snapshotId":"snap-1"`)
}
