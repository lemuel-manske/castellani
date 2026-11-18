package api_test

import (
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/stretchr/testify/assert"
)

func TestGateway_ArchiveSubmissionIsAcceptedAfterCoordinatorConfirmsAdmission(t *testing.T) {
	forwarded := make(chan struct {
		key  string
		body string
	}, 1)

	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)

		forwarded <- struct {
			key  string
			body string
		}{
			key:  r.Header.Get(httpx.IdempotencyHeader),
			body: string(body),
		}

		coordinatorAcceptsArchive(w, r)
	})

	result := gateway.submit(idempotencyKey, validSubmission)
	request := <-forwarded

	assert.Equal(t, http.StatusAccepted, result.Status)
	assert.Equal(t, "/archives/run-1", result.Header.Get(httpx.LocationHeader))
	assert.JSONEq(t, `{"archiveId":"run-1","status":"ACCEPTED","statusUrl":"/archives/run-1"}`, result.Body)
	assert.Equal(t, idempotencyKey, request.key)
	assert.JSONEq(t, validSubmission, request.body)
}

func TestGateway_ArchiveStatusReflectsCoordinatorState(t *testing.T) {
	gateway := startGateway(t, coordinatorReturnsArchiveStatus)

	result := gateway.get(httpx.ArchivePathPrefix + archiveID)

	assert.Equal(t, http.StatusOK, result.Status)
	assert.JSONEq(t, runningArchive, result.Body)
}

func TestGateway_RepeatedArchiveSubmissionAlwaysReachesCoordinator(t *testing.T) {
	var forwarded atomic.Int32

	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		forwarded.Add(1)
		coordinatorAcceptsArchive(w, r)
	})

	first := gateway.submit(idempotencyKey, validSubmission)
	second := gateway.submit(idempotencyKey, validSubmission)

	assert.Equal(t, http.StatusAccepted, first.Status)
	assert.Equal(t, http.StatusAccepted, second.Status)
	assert.EqualValues(t, 2, forwarded.Load())
}

func TestGateway_ConflictingArchiveSubmissionPreservesCoordinatorError(t *testing.T) {
	gateway := startGateway(t, coordinatorRejectsConflictingKey)

	result := gateway.submit(idempotencyKey, validSubmission)

	assert.Equal(t, http.StatusConflict, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
	assert.JSONEq(t, `{"type":"urn:coordinator:idempotency-conflict","title":"Conflict","status":409,"detail":"Key was used for different content.","instance":"/archives"}`, result.Body)
}

func TestGateway_ArchiveWithoutIdempotencyKeyIsRejectedBeforeForwarding(t *testing.T) {
	var forwarded atomic.Int32

	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		forwarded.Add(1)
		coordinatorAcceptsArchive(w, r)
	})

	result := gateway.submit("", validSubmission)

	assert.Equal(t, http.StatusBadRequest, result.Status)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_ArchiveWithUnknownFieldsIsRejectedBeforeForwarding(t *testing.T) {
	var forwarded atomic.Int32

	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		forwarded.Add(1)
		coordinatorAcceptsArchive(w, r)
	})

	body := `{"seedUrl":"https://example.org/","maxDepth":0,"maxPages":1,"unsupported":true}`
	result := gateway.submit(idempotencyKey, body)

	assert.Equal(t, http.StatusBadRequest, result.Status)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_ArchiveWithInvalidLimitsIsRejectedBeforeForwarding(t *testing.T) {
	var forwarded atomic.Int32

	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		forwarded.Add(1)
		coordinatorAcceptsArchive(w, r)
	})

	body := `{"seedUrl":"https://example.org/","maxDepth":-1,"maxPages":0}`
	result := gateway.submit(idempotencyKey, body)

	assert.Equal(t, http.StatusUnprocessableEntity, result.Status)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_OversizedArchiveIsRejectedBeforeForwarding(t *testing.T) {
	var forwarded atomic.Int32

	gateway := startGateway(t, func(w http.ResponseWriter, r *http.Request) {
		forwarded.Add(1)
		coordinatorAcceptsArchive(w, r)
	})

	oversizedBody := validSubmission + strings.Repeat(" ", 70<<10)
	result := gateway.submit(idempotencyKey, oversizedBody)

	assert.Equal(t, http.StatusBadRequest, result.Status)
	assert.Zero(t, forwarded.Load())
}

func TestGateway_CoordinatorDisconnectLeavesArchiveAdmissionUnconfirmed(t *testing.T) {
	gateway := startGateway(t, coordinatorDisconnects)

	result := gateway.submit(idempotencyKey, validSubmission)

	assert.Equal(t, http.StatusServiceUnavailable, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
	assert.Contains(t, result.Body, "Retry with the same Idempotency-Key")
}

func TestGateway_MalformedAdmissionIsNeverReportedAsAccepted(t *testing.T) {
	gateway := startGateway(t, coordinatorReturnsMalformedAdmission)

	result := gateway.submit(idempotencyKey, validSubmission)

	assert.Equal(t, http.StatusBadGateway, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
}

func TestGateway_StatusForDifferentArchiveIsNotReturned(t *testing.T) {
	gateway := startGateway(t, coordinatorReturnsMismatchedArchive)

	result := gateway.get(httpx.ArchivePathPrefix + archiveID)

	assert.Equal(t, http.StatusBadGateway, result.Status)
}

func TestGateway_UnknownRouteReturnsProblemDetails(t *testing.T) {
	gateway := startGateway(t, coordinatorIsUnused)

	result := gateway.get("/unknown")

	assert.Equal(t, http.StatusNotFound, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
	assert.NotEmpty(t, result.Header.Get("X-Request-ID"))
}

func TestGateway_UnsupportedMethodReturnsProblemDetails(t *testing.T) {
	gateway := startGateway(t, coordinatorIsUnused)

	result := gateway.put(httpx.ArchivePathPrefix + archiveID)

	assert.Equal(t, http.StatusMethodNotAllowed, result.Status)
	assert.Equal(t, httpx.MediaTypeProblem, result.Header.Get(httpx.HeaderContentType))
}

func TestGateway_LivenessDoesNotDependOnCoordinator(t *testing.T) {
	gateway := startGateway(t, coordinatorIsUnused)

	result := gateway.get("/health/live")

	assert.Equal(t, http.StatusOK, result.Status)
	assert.Equal(t, "ok\n", result.Body)
}

func TestGateway_ReadinessRejectsRequestsBeforeServerIsReady(t *testing.T) {
	gateway := startUnreadyGateway(t)

	result := gateway.get("/health/ready")

	assert.Equal(t, http.StatusServiceUnavailable, result.Status)
}
