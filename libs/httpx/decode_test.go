package httpx_test

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type requestBody struct {
	SeedURL string `json:"seedUrl"`
}

func TestDecodeJSONBytes_PreservesAcceptedRequestBytes(t *testing.T) {
	raw := `{ "seedUrl": "https://example.com/" }`
	request := httptest.NewRequest(http.MethodPost, "/archives", strings.NewReader(raw))
	request.Header.Set(httpx.HeaderContentType, "application/json; charset=utf-8")

	var body requestBody
	data, err := httpx.DecodeJSONBytes(httptest.NewRecorder(), request, &body)
	require.NoError(t, err)

	assert.Equal(t, raw, string(data))
	assert.Equal(t, "https://example.com/", body.SeedURL)
}

func TestDecodeJSONBytes_RejectsUnknownFields(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/archives", strings.NewReader(`{"seedUrl":"https://example.com/","extra":true}`))
	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)

	var body requestBody
	_, err := httpx.DecodeJSONBytes(httptest.NewRecorder(), request, &body)

	require.ErrorIs(t, err, httpx.ErrInvalidJSON)
}

func TestDecodeJSONBytes_RejectsMultipleValues(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/archives", strings.NewReader(`{} {}`))
	request.Header.Set(httpx.HeaderContentType, httpx.MediaTypeJSON)

	var body requestBody
	_, err := httpx.DecodeJSONBytes(httptest.NewRecorder(), request, &body)

	require.ErrorIs(t, err, httpx.ErrExtraJSON)
}

func TestDecodeJSONBytes_RejectsWrongContentType(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/archives", strings.NewReader(`{}`))
	request.Header.Set(httpx.HeaderContentType, "text/plain")

	var body requestBody
	_, err := httpx.DecodeJSONBytes(httptest.NewRecorder(), request, &body)

	require.ErrorIs(t, err, httpx.ErrContentType)
}

