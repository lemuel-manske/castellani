package main

import (
	"net/http"
	"testing"

	"github.com/lemuel-manske/castellani/services/gateway/internal/testutil"
	"github.com/stretchr/testify/require"
)

func TestGateway_GetWACZPreservesRangeContentLengthAndBytes(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`
	const body = "PK\x03\x04"

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
		testutil.Capture(
			testutil.Response{
				Status: http.StatusPartialContent,
				Headers: map[string]string{
					"Content-Type":   "application/wacz",
					"Content-Length": "4",
					"Content-Range":  "bytes 0-3/128",
					"Accept-Ranges":  "bytes",
					"ETag":           `"wacz-1"`,
				},
				Body: body,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Send(
		t,
		http.MethodGet,
		gateway,
		"/archives/archive-1/wacz",
		"",
		map[string]string{"Range": "bytes=0-3"},
	)

	require.Equal(t, http.StatusPartialContent, response.Status)
	require.Equal(t, "4", response.Header.Get("Content-Length"))
	require.Equal(t, "bytes 0-3/128", response.Header.Get("Content-Range"))
	require.Equal(t, "application/wacz", response.Header.Get("Content-Type"))
	require.Equal(t, body, response.Body)

	requests := upstreams.Capture.Requests()
	require.Len(t, requests, 1)
	require.Equal(t, "bytes=0-3", requests[0].Headers.Get("Range"))
}
