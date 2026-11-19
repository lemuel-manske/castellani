package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/lemuel-manske/unnamed/services/coordinator/api"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const submission = `{"seedUrl":"https://example.com/","maxDepth":2,"maxPages":4}`

type fixture struct {
	mu       sync.Mutex
	byKey    map[string]record
	byID     map[string]archive.Status
	admitted int
}
type record struct {
	digest   string
	accepted archive.AcceptedResponse
}

func newFixture(t *testing.T) (*fixture, *httptest.Server) {
	t.Helper()
	f := &fixture{byKey: make(map[string]record), byID: make(map[string]archive.Status)}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	server := httptest.NewServer(api.NewRouter(application.New(f), func() bool { return true }, logger))
	t.Cleanup(server.Close)
	return f, server
}

func (f *fixture) Admit(_ context.Context, key, digest string, accepted archive.AcceptedResponse, _ archive.Submission, _ time.Time) (archive.AcceptedResponse, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if previous, ok := f.byKey[key]; ok {
		if previous.digest != digest {
			return archive.AcceptedResponse{}, application.ErrConflict
		}
		return previous.accepted, nil
	}
	f.admitted++
	f.byKey[key] = record{digest: digest, accepted: accepted}
	f.byID[accepted.ArchiveID] = archive.Status{ArchiveID: accepted.ArchiveID, Status: archive.Accepted, Replay: archive.Replay{Status: "NOT_READY"}, Search: archive.Search{Status: "PENDING"}}
	return accepted, nil
}
func (f *fixture) Status(_ context.Context, id string) (archive.Status, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	result, ok := f.byID[id]
	if !ok {
		return archive.Status{}, application.ErrNotFound
	}
	return result, nil
}
func (f *fixture) Count() int { f.mu.Lock(); defer f.mu.Unlock(); return f.admitted }

func post(t *testing.T, client *http.Client, base, key, body string) *http.Response {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, base+"/archives", bytes.NewBufferString(body))
	require.NoError(t, err)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", key)
	response, err := client.Do(req)
	require.NoError(t, err)
	t.Cleanup(func() { _ = response.Body.Close() })
	return response
}

func accepted(t *testing.T, response *http.Response) archive.AcceptedResponse {
	t.Helper()
	require.Equal(t, http.StatusAccepted, response.StatusCode)
	var document archive.AcceptedResponse
	require.NoError(t, json.NewDecoder(response.Body).Decode(&document))
	require.NotEmpty(t, document.ArchiveID)
	return document
}

func TestArchive_SubmissionIsImmediatelyVisible(t *testing.T) {
	_, server := newFixture(t)
	created := accepted(t, post(t, server.Client(), server.URL, "a-unique-key", submission))
	response, err := server.Client().Get(server.URL + created.StatusURL)
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusOK, response.StatusCode)
	var document archive.Status
	require.NoError(t, json.NewDecoder(response.Body).Decode(&document))

	assert.Equal(t, created.ArchiveID, document.ArchiveID)
	assert.Equal(t, archive.Accepted, document.Status)
	assert.Equal(t, "NOT_READY", document.Replay.Status)
	assert.Equal(t, "PENDING", document.Search.Status)
}

func TestArchive_SameKeyAndSemanticallyIdenticalBodyReusesAdmission(t *testing.T) {
	fixture, server := newFixture(t)
	first := accepted(t, post(t, server.Client(), server.URL, "same-key-123", submission))
	second := accepted(t, post(t, server.Client(), server.URL, "same-key-123", `{ "maxPages":4,"maxDepth":2,"seedUrl":"https://example.com/" }`))

	assert.Equal(t, first, second)
	assert.Equal(t, 1, fixture.Count())
}

func TestArchive_SameKeyWithDifferentBodyReturnsConflict(t *testing.T) {
	fixture, server := newFixture(t)
	accepted(t, post(t, server.Client(), server.URL, "same-key-123", submission))
	response := post(t, server.Client(), server.URL, "same-key-123", `{"seedUrl":"https://example.com/other","maxDepth":2,"maxPages":4}`)

	assert.Equal(t, http.StatusConflict, response.StatusCode)
	assert.Equal(t, "application/problem+json", response.Header.Get("Content-Type"))
	assert.Equal(t, 1, fixture.Count())
}

func TestArchive_InvalidSubmissionDoesNotAdmitWork(t *testing.T) {
	fixture, server := newFixture(t)
	response := post(t, server.Client(), server.URL, "valid-key-123", `{"seedUrl":"file:///etc/passwd","maxDepth":2,"maxPages":4}`)

	assert.Equal(t, http.StatusUnprocessableEntity, response.StatusCode)
	assert.Zero(t, fixture.Count())
}

func TestArchive_UnknownFieldsAreRejected(t *testing.T) {
	fixture, server := newFixture(t)
	response := post(t, server.Client(), server.URL, "valid-key-123", `{"seedUrl":"https://example.com","maxDepth":2,"maxPages":4,"unexpected":true}`)

	assert.Equal(t, http.StatusBadRequest, response.StatusCode)
	assert.Zero(t, fixture.Count())
}

func TestArchive_UnknownArchiveIsNotFound(t *testing.T) {
	_, server := newFixture(t)
	response, err := server.Client().Get(server.URL + "/archives/not-present")
	require.NoError(t, err)
	defer response.Body.Close()

	assert.Equal(t, http.StatusNotFound, response.StatusCode)
}
