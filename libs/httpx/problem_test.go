package httpx_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWriteProblem_EmitsStandardProblemDocument(t *testing.T) {
	request := httptest.NewRequest(
		http.MethodGet,
		"/archives/missing",
		nil,
	)
	response := httptest.NewRecorder()

	problem := httpx.NewProblem(
		request,
		http.StatusNotFound,
		"not-found",
		"Not Found",
		"Archive does not exist.",
	)
	httpx.WriteProblem(response, problem)

	assert.Equal(
		t,
		http.StatusNotFound,
		response.Code,
	)
	assert.Equal(
		t,
		httpx.MediaTypeProblem,
		response.Header().Get(httpx.HeaderContentType),
	)
	assert.Equal(
		t,
		httpx.CacheNoStore,
		response.Header().Get(httpx.HeaderCacheControl),
	)

	var document httpx.Problem
	require.NoError(t, json.Unmarshal(response.Body.Bytes(), &document))

	assert.Equal(
		t,
		httpx.ProblemTypePrefix+"not-found",
		document.Type,
	)
	assert.Equal(
		t,
		"/archives/missing",
		document.Instance,
	)
}
