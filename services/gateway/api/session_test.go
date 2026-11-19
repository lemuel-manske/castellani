package api_test

import (
	"io"
	"net/http"
	"testing"

	sharedhttp "github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/gatewaytest"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/stretchr/testify/assert"
)

const (
	sessionRequest = `{"archiveId":"run-1","targetUrl":"https://example.org/login"}`
	sessionCreated = `{"sessionId":"sess-1","archiveId":"run-1","status":"CREATED","expiresAt":"2026-11-18T23:00:00Z"}`
)

func TestGateway_CreateSessionRetainsIdempotencyKeyAndPublicLocation(t *testing.T) {
	keys := make(chan string, 1)
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, r *http.Request) {
		keys <- r.Header.Get(sharedhttp.IdempotencyHeader)
		w.Header().Set(sharedhttp.HeaderContentType, sharedhttp.MediaTypeJSON)
		w.Header().Set(sharedhttp.LocationHeader, "http://capture.internal/private/sess-1")
		w.WriteHeader(http.StatusCreated)
		_, _ = io.WriteString(w, sessionCreated)
	}))

	result := gateway.CreateSession(gatewaytest.IdempotencyKey, sessionRequest)

	assert.Equal(t, http.StatusCreated, result.Status)
	assert.JSONEq(t, sessionCreated, result.Body)
	assert.Equal(t, "/sessions/sess-1", result.Header.Get(sharedhttp.LocationHeader))
	assert.Equal(t, gatewaytest.IdempotencyKey, <-keys)
}

func TestGateway_CreateSessionWithoutIdempotencyKeyIsRejected(t *testing.T) {
	gateway := gatewaytest.Start(t)

	result := gateway.CreateSession("", sessionRequest)

	assert.Equal(t, http.StatusBadRequest, result.Status)
}

func TestGateway_CreateSessionRejectsNonHTTPSTarget(t *testing.T) {
	gateway := gatewaytest.Start(t)

	result := gateway.CreateSession(gatewaytest.IdempotencyKey, `{"archiveId":"run-1","targetUrl":"file:///etc/passwd"}`)

	assert.Equal(t, http.StatusBadRequest, result.Status)
}

func TestGateway_SessionFinalizationForwardsDesiredState(t *testing.T) {
	received := make(chan string, 1)
	gateway := gatewaytest.Start(t, gatewaytest.WithCaptureService(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		received <- string(body)
		w.Header().Set(sharedhttp.HeaderContentType, sharedhttp.MediaTypeJSON)
		_, _ = io.WriteString(w, `{"sessionId":"sess-1","archiveId":"run-1","status":"COMPLETED","expiresAt":"2026-11-18T23:00:00Z","authGeneration":1}`)
	}))

	result := gateway.UpdateSession("sess-1", `{"status":"COMPLETED"}`)

	assert.Equal(t, http.StatusOK, result.Status)
	assert.JSONEq(t, `{"status":"COMPLETED"}`, <-received)
	assert.Contains(t, result.Body, `"authGeneration":1`)
}

func TestGateway_SessionFinalizationRejectsInvalidTransition(t *testing.T) {
	gateway := gatewaytest.Start(t)

	result := gateway.UpdateSession("sess-1", `{"status":"ACTIVE"}`)

	assert.Equal(t, http.StatusBadRequest, result.Status)
}
