package api_test

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/coordinatortest"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestArchive_SubmissionIsImmediatelyVisible(t *testing.T) {
	service := coordinatortest.StartHTTP(t)
	created := coordinatortest.Accepted(t, service.Submit(t, coordinatortest.ArchiveKey, coordinatortest.Submission))
	response := service.Get(t, created.ArchiveID)

	require.Equal(t, http.StatusOK, response.StatusCode)

	var document archive.Status
	require.NoError(t, json.NewDecoder(response.Body).Decode(&document))

	assert.Equal(t, created.ArchiveID, document.ArchiveID)
	assert.Equal(t, archive.Accepted, document.Status)
	assert.Equal(t, "NOT_READY", document.Replay.Status)
	assert.Equal(t, "PENDING", document.Search.Status)
}

func TestArchive_SameKeyAndSemanticallyIdenticalBodyReusesAdmission(t *testing.T) {
	service := coordinatortest.StartHTTP(t)
	first := coordinatortest.Accepted(t, service.Submit(t, coordinatortest.ArchiveKey, coordinatortest.Submission))
	second := coordinatortest.Accepted(t, service.Submit(t, coordinatortest.ArchiveKey, `{"maxPages":4,"maxDepth":2,"seedUrl":"https://example.com/"}`))

	assert.Equal(t, first, second)
	assert.Equal(t, 1, service.Archives.AdmissionCount())
}

func TestArchive_SameKeyWithDifferentBodyReturnsConflict(t *testing.T) {
	service := coordinatortest.StartHTTP(t)
	coordinatortest.Accepted(t, service.Submit(t, coordinatortest.ArchiveKey, coordinatortest.Submission))

	response := service.Submit(t, coordinatortest.ArchiveKey, `{"seedUrl":"https://example.com/other","maxDepth":2,"maxPages":4}`)

	assert.Equal(t, http.StatusConflict, response.StatusCode)
	assert.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))
	assert.Equal(t, 1, service.Archives.AdmissionCount())
}

func TestArchive_InvalidSubmissionDoesNotAdmitWork(t *testing.T) {
	service := coordinatortest.StartHTTP(t)
	response := service.Submit(t, coordinatortest.ArchiveKey, `{"seedUrl":"file:///etc/passwd","maxDepth":2,"maxPages":4}`)

	assert.Equal(t, http.StatusUnprocessableEntity, response.StatusCode)
	assert.Zero(t, service.Archives.AdmissionCount())
}

func TestArchive_UnknownFieldsAreRejected(t *testing.T) {
	service := coordinatortest.StartHTTP(t)
	response := service.Submit(t, coordinatortest.ArchiveKey, `{"seedUrl":"https://example.com","maxDepth":2,"maxPages":4,"unexpected":true}`)

	assert.Equal(t, http.StatusBadRequest, response.StatusCode)
	assert.Zero(t, service.Archives.AdmissionCount())
}

func TestArchive_UnknownArchiveIsNotFound(t *testing.T) {
	service := coordinatortest.StartHTTP(t)
	response := service.Get(t, "not-present")

	assert.Equal(t, http.StatusNotFound, response.StatusCode)
}
