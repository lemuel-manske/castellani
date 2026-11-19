package api_test

import (
 "io"
 "net/http"
 "testing"

 "github.com/lemuel-manske/castellani/libs/httpx"
 "github.com/lemuel-manske/unnamed/services/gateway/gatewaytest"
 "github.com/stretchr/testify/assert"
)

func TestGateway_MalformedPageMetadataReturnsBadGateway(t *testing.T) {
 gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
  w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
  _, _ = io.WriteString(w, `{"items":null}`)
 }))

 result := gateway.Get("/archives/run-1/pages")

 assert.Equal(t, http.StatusBadGateway, result.Status)
 assert.Contains(t, result.Body, "invalid-upstream")
}

func TestGateway_MismatchedSnapshotMetadataReturnsBadGateway(t *testing.T) {
 gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
  w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
  _, _ = io.WriteString(w, `{"archiveId":"wrong-run","snapshotId":"snap-1","url":"https://example.org/","capturedAt":"2026-11-18T12:00:00Z"}`)
 }))

 result := gateway.Get("/archives/run-1/snapshots/snap-1")

 assert.Equal(t, http.StatusBadGateway, result.Status)
 assert.Contains(t, result.Body, "invalid-upstream")
}

func TestGateway_SearchMalformedResponseReturnsBadGateway(t *testing.T) {
 gateway := gatewaytest.Start(t, gatewaytest.WithSearchService(func(w http.ResponseWriter, _ *http.Request) {
  w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
  _, _ = io.WriteString(w, `{"results":null}`)
 }))

 result := gateway.Get("/search?q=archive")

 assert.Equal(t, http.StatusBadGateway, result.Status)
 assert.Contains(t, result.Body, "invalid-upstream")
}

func TestGateway_CaptureProblemIsForwardedWithoutLosingDetails(t *testing.T) {
 gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
  w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeProblem)
  w.WriteHeader(http.StatusConflict)
  _, _ = io.WriteString(w, `{"type":"urn:capture:conflict","title":"Conflict","status":409,"detail":"Session is already finalized."}`)
 }))

 result := gateway.Get("/sessions/sess-1")

 assert.Equal(t, http.StatusConflict, result.Status)
 assert.JSONEq(t, `{"type":"urn:capture:conflict","title":"Conflict","status":409,"detail":"Session is already finalized.","instance":"/sessions/sess-1"}`, result.Body)
}

func TestGateway_InvalidCreatedSessionIsNotPublished(t *testing.T) {
 gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
  w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
  w.WriteHeader(http.StatusCreated)
  _, _ = io.WriteString(w, `{"sessionId":"sess-1","archiveId":"another-run","status":"CREATED","expiresAt":"2026-11-18T23:00:00Z"}`)
 }))

 result := gateway.CreateSession(gatewaytest.IdempotencyKey, `{"archiveId":"run-1","targetUrl":"https://example.org/login"}`)

 assert.Equal(t, http.StatusBadGateway, result.Status)
 assert.Empty(t, result.Header.Get(httpx.LocationHeader))
}

func TestGateway_InvalidWACZContentTypeReturnsBadGateway(t *testing.T) {
 gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, _ *http.Request) {
  w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
  _, _ = io.WriteString(w, `{"not":"wacz"}`)
 }))

 result := gateway.WACZ("run-1", "", "")

 assert.Equal(t, http.StatusBadGateway, result.Status)
 assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
}
