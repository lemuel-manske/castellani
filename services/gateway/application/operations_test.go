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

	app := application.NewApplicationWithServices(nil, nil, search.NewClient(*origin, time.Second))
	limit := 10
	result, err := app.Search(context.Background(), application.SearchQuery{
		Text: "archive", ArchiveID: "run-1", Pagination: application.Pagination{Limit: &limit},
	})
	require.NoError(t, err)

	assert.JSONEq(t, `{"results":[]}`, string(result))
	assert.Equal(t, "archive", (<-received).Get("q"))
}

func TestSearch_InvalidQueryIsRejectedBeforeCallingService(t *testing.T) {
	app := application.NewApplicationWithServices(nil, nil, nil)

	_, err := app.Search(context.Background(), application.SearchQuery{Text: " "})

	require.ErrorIs(t, err, application.ErrInvalidSearch)
}

func TestSnapshot_MismatchedServiceResponseIsRejected(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"archiveId":"another-run","snapshotId":"snap-1","url":"https://example.org/","capturedAt":"2026-11-18T12:00:00Z"}`)
	}))
	t.Cleanup(service.Close)

	origin, err := url.Parse(service.URL)
	require.NoError(t, err)

	client := capture.NewClient(*origin, time.Second, time.Second)
	app := application.NewApplicationWithServices(nil, client, nil)

	_, err = app.GetSnapshot(context.Background(), "run-1", "snap-1")

	require.ErrorIs(t, err, application.ErrInvalidUpstream)
}

func TestSession_InvalidTransitionIsRejectedBeforeCallingService(t *testing.T) {
	app := application.NewApplicationWithServices(nil, nil, nil)

	_, err := app.UpdateSession(context.Background(), "session-1", "ACTIVE", []byte(`{"status":"ACTIVE"}`))

	require.ErrorIs(t, err, application.ErrInvalidSession)
}

func TestWACZ_PartialContentIsStreamedByCapture(t *testing.T) {
	service := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "bytes=0-3", r.Header.Get("Range"))
		w.Header().Set("Content-Type", "application/wacz")
		w.Header().Set("Content-Range", "bytes 0-3/8")
		w.WriteHeader(http.StatusPartialContent)
		_, _ = io.WriteString(w, "WACZ")
	}))
	t.Cleanup(service.Close)

	origin, err := url.Parse(service.URL)
	require.NoError(t, err)

	client := capture.NewClient(*origin, time.Second, time.Second)
	app := application.NewApplicationWithServices(nil, client, nil)

	response, err := app.GetWACZ(context.Background(), "run-1", application.WACZOptions{Range: "bytes=0-3"})
	require.NoError(t, err)
	t.Cleanup(func() { _ = response.Body.Close() })

	data, err := io.ReadAll(response.Body)
	require.NoError(t, err)

	assert.True(t, response.Partial)
	assert.Equal(t, "bytes 0-3/8", response.ContentRange)
	assert.Equal(t, "WACZ", string(data))
}

func TestWACZ_MultipleRangesAreRejectedBeforeCallingService(t *testing.T) {
	app := application.NewApplicationWithServices(nil, nil, nil)

	_, err := app.GetWACZ(context.Background(), "run-1", application.WACZOptions{Range: "bytes=0-1,3-4"})

	require.True(t, errors.Is(err, application.ErrInvalidWACZRange))
}
