package application_test

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"

	"github.com/lemuel-manske/unnamed/services/gateway/application"
	"github.com/lemuel-manske/unnamed/services/gateway/assembly"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/capture"
	"github.com/lemuel-manske/unnamed/services/gateway/clients/search"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSearch_ValidQueryCallsSearchService(t *testing.T) {
	received := make(chan url.Values, 1)
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		received <- r.URL.Query()
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"results":[]}`)
	}))
	t.Cleanup(service.Close)

	origin, err := url.Parse(service.URL)
	require.NoError(t, err)

	app := assembly.NewApplication(
		nil,
		nil,
		search.NewClient(*origin, time.Second),
	)
	limit := 10
	result, err := app.Search(context.Background(), application.SearchQuery{
		Text: "archive", ArchiveID: "run-1", Pagination: application.Pagination{Limit: &limit},
	})
	require.NoError(t, err)

	assert.Empty(t, result.Results)
	assert.Equal(
		t,
		"archive",
		(<-received).Get("q"),
	)
}

func TestSearch_InvalidQueryIsRejectedBeforeCallingService(t *testing.T) {
	app := application.NewApplication(
		nil,
		nil,
		nil,
	)

	_, err := app.Search(context.Background(), application.SearchQuery{Text: " "})

	require.ErrorIs(
		t,
		err,
		application.ErrInvalidSearch,
	)
}

func TestSnapshot_MismatchedServiceResponseIsRejected(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"archiveId":"another-run","snapshotId":"snap-1","url":"https://example.org/","capturedAt":"2026-11-18T12:00:00Z"}`)
	}))
	t.Cleanup(service.Close)

	origin, err := url.Parse(service.URL)
	require.NoError(t, err)

	client := capture.NewClient(
		*origin,
		time.Second,
		time.Second,
	)
	app := assembly.NewApplication(
		nil,
		client,
		nil,
	)

	_, err = app.GetSnapshot(
		context.Background(),
		"run-1",
		"snap-1",
	)

	require.ErrorIs(
		t,
		err,
		application.ErrInvalidUpstream,
	)
}

func TestSession_InvalidTransitionIsRejectedBeforeCallingService(t *testing.T) {
	app := application.NewApplication(
		nil,
		nil,
		nil,
	)

	_, err := app.UpdateSession(
		context.Background(),
		"session-1",
		"ACTIVE",
		[]byte(`{"status":"ACTIVE"}`),
	)

	require.ErrorIs(
		t,
		err,
		application.ErrInvalidSession,
	)
}

func TestWACZ_PartialContentIsStreamedByCapture(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(
			t,
			"bytes=0-3",
			r.Header.Get("Range"),
		)
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Content-Range", "bytes 0-3/8")

		w.WriteHeader(http.StatusPartialContent)
		_, _ = io.WriteString(w, "WACZ")
	}))
	t.Cleanup(service.Close)

	origin, err := url.Parse(service.URL)
	require.NoError(t, err)

	client := capture.NewClient(
		*origin,
		time.Second,
		time.Second,
	)
	app := assembly.NewApplication(
		nil,
		client,
		nil,
	)

	response, err := app.GetWACZ(
		context.Background(),
		"run-1",
		application.WACZOptions{Range: "bytes=0-3"},
	)
	require.NoError(t, err)
	t.Cleanup(func() { _ = response.Body.Close() })

	data, err := io.ReadAll(response.Body)
	require.NoError(t, err)

	assert.True(t, response.Partial)
	assert.Equal(
		t,
		"bytes 0-3/8",
		response.ContentRange,
	)
	assert.Equal(
		t,
		"WACZ",
		string(data),
	)
}

func TestWACZ_MultipleRangesAreRejectedBeforeCallingService(t *testing.T) {
	app := application.NewApplication(
		nil,
		nil,
		nil,
	)

	_, err := app.GetWACZ(
		context.Background(),
		"run-1",
		application.WACZOptions{Range: "bytes=0-1,3-4"},
	)

	require.True(t, errors.Is(err, application.ErrInvalidWACZRange))
}

func TestSearch_ServiceFailureIsMappedToApplicationError(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/problem+json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = io.WriteString(w, `{"type":"urn:search:unavailable","title":"Unavailable","status":503}`)
	}))
	t.Cleanup(service.Close)

	origin, err := url.Parse(service.URL)
	require.NoError(t, err)

	app := assembly.NewApplication(
		nil,
		nil,
		search.NewClient(*origin, time.Second),
	)
	_, err = app.Search(context.Background(), application.SearchQuery{Text: "archive"})

	var failure *application.DependencyFailure
	require.ErrorAs(
		t,
		err,
		&failure,
	)

	assert.Equal(
		t,
		http.StatusServiceUnavailable,
		failure.Status,
	)
	assert.Equal(
		t,
		"urn:search:unavailable",
		failure.Type,
	)
}

func TestSession_CreateMapsCaptureResponseIntoApplicationSession(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_, _ = io.WriteString(w, `{"sessionId":"sess-1","archiveId":"run-1","status":"CREATED","expiresAt":"2026-11-18T23:00:00Z","authGeneration":3}`)
	}))
	t.Cleanup(service.Close)

	origin, err := url.Parse(service.URL)
	require.NoError(t, err)

	app := assembly.NewApplication(
		nil,
		capture.NewClient(
			*origin,
			time.Second,
			time.Second,
		),
		nil,
	)
	session, err := app.CreateSession(
		context.Background(),
		"sample-key-123",
		application.SessionRequest{ArchiveID: "run-1", TargetURL: "https://example.org/login"},
		[]byte(`{"archiveId":"run-1","targetUrl":"https://example.org/login"}`),
	)
	require.NoError(t, err)
	require.NotNil(t, session.AuthGeneration)

	assert.Equal(
		t,
		"sess-1",
		session.SessionID,
	)
	assert.Equal(
		t,
		"run-1",
		session.ArchiveID,
	)
	assert.Equal(
		t,
		3,
		*session.AuthGeneration,
	)
}
