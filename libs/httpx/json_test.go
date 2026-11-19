package httpx_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/stretchr/testify/assert"
)

func TestJSON_EmitsUncachedJSON(t *testing.T) {
	response := httptest.NewRecorder()

	httpx.JSON(response, http.StatusAccepted, map[string]string{"status": "ACCEPTED"})

	assert.Equal(t, http.StatusAccepted, response.Code)
	assert.Equal(t, httpx.MediaTypeJSON, response.Header().Get(httpx.HeaderContentType))
	assert.Equal(t, httpx.CacheNoStore, response.Header().Get(httpx.HeaderCacheControl))
	assert.JSONEq(t, `{"status":"ACCEPTED"}`, response.Body.String())
}
