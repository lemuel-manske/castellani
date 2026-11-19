package api_test

import (
	"io"
	"net/http"
	"strings"
	"testing"

	sharedhttp "github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/gatewaytest"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/stretchr/testify/assert"
)

func TestGateway_PublishedWACZStreamsBytesWithoutRewriting(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Accept-Ranges", "bytes")
		w.Header().Set("ETag", `"digest-1"`)
		_, _ = io.WriteString(w, "WACZ-PAYLOAD")
	}))

	result := gateway.WACZ("run-1", "", "")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Equal(t, "WACZ-PAYLOAD", result.Body)
	assert.Equal(t, "bytes", result.Header.Get("Accept-Ranges"))
	assert.Equal(t, `"digest-1"`, result.Header.Get("ETag"))
}

func TestGateway_WACZRangeRequestPreservesPartialContentSemantics(t *testing.T) {
	receivedRange := make(chan string, 1)
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, r *http.Request) {
		receivedRange <- r.Header.Get("Range")
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Accept-Ranges", "bytes")
		w.Header().Set("Content-Range", "bytes 0-3/8")
		w.WriteHeader(http.StatusPartialContent)
		_, _ = io.WriteString(w, "WACZ")
	}))

	result := gateway.WACZ("run-1", "bytes=0-3", "")

	assert.Equal(t, http.StatusPartialContent, result.Status)
	assert.Equal(t, "bytes=0-3", <-receivedRange)
	assert.Equal(t, "bytes 0-3/8", result.Header.Get("Content-Range"))
	assert.Equal(t, "WACZ", result.Body)
}

func TestGateway_WACZHeadReturnsMetadataWithoutReadingBytes(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Content-Length", "900")
		w.Header().Set("ETag", `"digest-1"`)
		w.WriteHeader(http.StatusOK)
	}))

	result := gateway.Head("/archives/run-1/wacz")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Empty(t, result.Body)
	assert.Equal(t, "900", result.Header.Get("Content-Length"))
}

func TestGateway_UnpublishedWACZIsNotExposed(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(sharedhttp.HeaderContentType, sharedhttp.MediaTypeProblem)
		w.WriteHeader(http.StatusNotFound)
		_, _ = io.WriteString(w, `{"type":"urn:capture:unpublished","title":"Not Found","status":404}`)
	}))

	result := gateway.WACZ("run-1", "", "")

	assert.Equal(t, http.StatusNotFound, result.Status)
	assert.Equal(t, sharedhttp.MediaTypeProblem, result.Header.Get(sharedhttp.HeaderContentType))
	assert.NotContains(t, strings.ToLower(result.Body), "s3://")
}

func TestGateway_WACZUnsatisfiableRangePreservesContentRange(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set(sharedhttp.HeaderContentType, sharedhttp.MediaTypeProblem)
		w.Header().Set("Content-Range", "bytes */8")
		w.WriteHeader(http.StatusRequestedRangeNotSatisfiable)
		_, _ = io.WriteString(w, `{"type":"urn:capture:range","title":"Range Not Satisfiable","status":416}`)
	}))

	result := gateway.WACZ("run-1", "bytes=900-1000", "")

	assert.Equal(t, http.StatusRequestedRangeNotSatisfiable, result.Status)
	assert.Equal(t, "bytes */8", result.Header.Get("Content-Range"))
}

func TestGateway_MultipleWACZRangesAreRejectedBeforeCapture(t *testing.T) {
	gateway := gatewaytest.Start(t)

	result := gateway.WACZ("run-1", "bytes=0-1,3-4", "")

	assert.Equal(t, http.StatusBadRequest, result.Status)
}
