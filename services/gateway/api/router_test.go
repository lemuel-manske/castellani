package api_test

import (
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/common"
	"github.com/lemuel-manske/unnamed/services/gateway/gatewaytest"
	"github.com/stretchr/testify/assert"
)

func TestGateway_ArchiveSubmissionIsAcceptedAfterCoordinatorConfirmsAdmission(t *testing.T) {
	forwarded := make(chan struct {
		key  string
		body string
	}, 1)

	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)

		forwarded <- struct {
			key  string
			body string
		}{
			key:  r.Header.Get(httpx.IdempotencyHeader),
			body: string(body),
		}

		gatewaytest.AcceptArchive(w, r)
	}))

	result := gateway.Submit(gatewaytest.IdempotencyKey, gatewaytest.ValidSubmission)
	request := <-forwarded

	assert.Equal(t, http.StatusAccepted, result.Status)
	assert.Equal(t, "/archives/run-1", result.Header.Get(httpx.LocationHeader))
	assert.JSONEq(t, `{"archiveId":"run-1","status":"ACCEPTED","statusUrl":"/archives/run-1"}`, result.Body)
	assert.Equal(t, gatewaytest.IdempotencyKey, request.key)
	assert.JSONEq(t, gatewaytest.ValidSubmission, request.body)
}

func TestGateway_ArchiveStatusReflectsCoordinatorState(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.ReturnArchiveStatus))

	result := gateway.Get(common.ArchivePathPrefix + gatewaytest.ArchiveID)

	assert.Equal(t, http.StatusOK, result.Status)
	assert.JSONEq(t, gatewaytest.RunningArchive, result.Body)
}

func TestGateway_RepeatedArchiveSubmissionAlwaysReachesCoordinator(t *testing.T) {
	coordinator := &gatewaytest.RecordingCoordinator{}
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(coordinator.Accept))

	first := gateway.Submit(gatewaytest.IdempotencyKey, gatewaytest.ValidSubmission)
	second := gateway.Submit(gatewaytest.IdempotencyKey, gatewaytest.ValidSubmission)

	assert.Equal(t, http.StatusAccepted, first.Status)
	assert.Equal(t, http.StatusAccepted, second.Status)
	assert.EqualValues(t, 2, coordinator.CallCount())
}

func TestGateway_ConflictingArchiveSubmissionPreservesCoordinatorError(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.RejectConflictingKey))

	result := gateway.Submit(gatewaytest.IdempotencyKey, gatewaytest.ValidSubmission)

	assert.Equal(t, http.StatusConflict, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
	assert.JSONEq(t, `{"type":"urn:coordinator:idempotency-conflict","title":"Conflict","status":409,"detail":"Key was used for different content.","instance":"/archives"}`, result.Body)
}

func TestGateway_ArchiveWithoutIdempotencyKeyIsRejectedBeforeForwarding(t *testing.T) {
	coordinator := &gatewaytest.RecordingCoordinator{}
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(coordinator.Accept))

	result := gateway.Submit("", gatewaytest.ValidSubmission)

	assert.Equal(t, http.StatusBadRequest, result.Status)
	assert.Zero(t, coordinator.CallCount())
}

func TestGateway_ArchiveWithUnknownFieldsIsRejectedBeforeForwarding(t *testing.T) {
	coordinator := &gatewaytest.RecordingCoordinator{}
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(coordinator.Accept))

	body := `{"seedUrl":"https://example.org/","maxDepth":0,"maxPages":1,"unsupported":true}`
	result := gateway.Submit(gatewaytest.IdempotencyKey, body)

	assert.Equal(t, http.StatusBadRequest, result.Status)
	assert.Zero(t, coordinator.CallCount())
}

func TestGateway_ArchiveWithInvalidLimitsIsRejectedBeforeForwarding(t *testing.T) {
	coordinator := &gatewaytest.RecordingCoordinator{}
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(coordinator.Accept))

	body := `{"seedUrl":"https://example.org/","maxDepth":-1,"maxPages":0}`
	result := gateway.Submit(gatewaytest.IdempotencyKey, body)

	assert.Equal(t, http.StatusUnprocessableEntity, result.Status)
	assert.Zero(t, coordinator.CallCount())
}

func TestGateway_OversizedArchiveIsRejectedBeforeForwarding(t *testing.T) {
	coordinator := &gatewaytest.RecordingCoordinator{}
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(coordinator.Accept))

	oversizedBody := gatewaytest.ValidSubmission + strings.Repeat(" ", 70<<10)
	result := gateway.Submit(gatewaytest.IdempotencyKey, oversizedBody)

	assert.Equal(t, http.StatusBadRequest, result.Status)
	assert.Zero(t, coordinator.CallCount())
}

func TestGateway_CoordinatorDisconnectLeavesArchiveAdmissionUnconfirmed(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.Disconnect))

	result := gateway.Submit(gatewaytest.IdempotencyKey, gatewaytest.ValidSubmission)

	assert.Equal(t, http.StatusServiceUnavailable, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
	assert.Contains(t, result.Body, "Retry with the same Idempotency-Key")
}

func TestGateway_MalformedAdmissionIsNeverReportedAsAccepted(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.ReturnMalformedAdmission))

	result := gateway.Submit(gatewaytest.IdempotencyKey, gatewaytest.ValidSubmission)

	assert.Equal(t, http.StatusBadGateway, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
}

func TestGateway_StatusForDifferentArchiveIsNotReturned(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.ReturnMismatchedArchive))

	result := gateway.Get(common.ArchivePathPrefix + gatewaytest.ArchiveID)

	assert.Equal(t, http.StatusBadGateway, result.Status)
}

func TestGateway_UnknownRouteReturnsProblemDetails(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.Unused))

	result := gateway.Get("/unknown")

	assert.Equal(t, http.StatusNotFound, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
	assert.NotEmpty(t, result.Header.Get("X-Request-ID"))
}

func TestGateway_UnsupportedMethodReturnsProblemDetails(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.Unused))

	result := gateway.Put(common.ArchivePathPrefix + gatewaytest.ArchiveID)

	assert.Equal(t, http.StatusMethodNotAllowed, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
}

func TestGateway_LivenessDoesNotDependOnCoordinator(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithCoordinatorService(gatewaytest.Unused))

	result := gateway.Get("/health/live")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Equal(t, "ok\n", result.Body)
}

func TestGateway_ReadinessRejectsRequestsBeforeServerIsReady(t *testing.T) {
	gateway := gatewaytest.Start(t, gatewaytest.WithReadiness(false))

	result := gateway.Get("/health/ready")

	assert.Equal(t, http.StatusServiceUnavailable, result.Status)
}
