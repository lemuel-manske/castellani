package coordinatortest

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lemuel-manske/unnamed/services/coordinator/api"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
	"github.com/stretchr/testify/require"
)

const (
	Submission = `{"seedUrl":"https://example.com/","maxDepth":2,"maxPages":4}`
	ArchiveKey = "archive-key-123"
)

type HTTP struct {
	URL     string
	Client  *http.Client
	Archives *Archives
}

func StartHTTP(t *testing.T) *HTTP {
	t.Helper()

	archives := NewArchives()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	server := httptest.NewServer(api.NewRouter(application.New(archives), func() bool { return true }, logger))
	t.Cleanup(server.Close)

	return &HTTP{
		URL:      server.URL,
		Client:   server.Client(),
		Archives: archives,
	}
}

func (h *HTTP) Submit(t *testing.T, key, body string) *http.Response {
	t.Helper()

	request, err := http.NewRequest(http.MethodPost, h.URL+"/archives", bytes.NewBufferString(body))
	require.NoError(t, err)

	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", key)

	response, err := h.Client.Do(request)
	require.NoError(t, err)
	t.Cleanup(func() { _ = response.Body.Close() })

	return response
}

func Accepted(t *testing.T, response *http.Response) archive.AcceptedResponse {
	t.Helper()
	require.Equal(t, http.StatusAccepted, response.StatusCode)

	var document archive.AcceptedResponse
	require.NoError(t, json.NewDecoder(response.Body).Decode(&document))
	require.NotEmpty(t, document.ArchiveID)

	return document
}

func (h *HTTP) Get(t *testing.T, id string) *http.Response {
	t.Helper()

	response, err := h.Client.Get(h.URL + "/archives/" + id)
	require.NoError(t, err)
	t.Cleanup(func() { _ = response.Body.Close() })

	return response
}
