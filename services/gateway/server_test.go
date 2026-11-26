package main

import (
	"net/http"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/services/gateway/internal/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGateway_GetArchiveReturnsCoordinatorStatus(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1",
	)

	assert.JSONEq(
		t,
		status,
		response.Body,
	)
}

func TestGateway_GetArchiveRejectsInvalidUpstreamResponse(t *testing.T) {
	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(`not json`)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1",
	)

	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:invalid-upstream",
			"title": "Invalid Upstream Response",
			"status": 502,
			"detail": "Coordinator returned an unexpected response.",
			"instance": "/archives/archive-1"
		}`,
		response.Body,
	)
}

func TestGateway_PagesRejectsUnpublishedArchive(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "REJECT",
		"replay": {"status": "READY"}
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1/pages",
	)

	assert.Equal(
		t,
		http.StatusNotFound,
		response.Status,
	)
	assert.Empty(t, upstreams.Capture.Requests())
}

func TestGateway_PagesReturnsCapturePages(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`
	pages := `{"items":[]}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
		testutil.Capture(testutil.OK(pages)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1/pages",
	)

	assert.JSONEq(
		t,
		pages,
		response.Body,
	)
}

func TestGateway_SearchReturnsResults(t *testing.T) {
	results := `{
		"results": [{"snapshotId": "snapshot-1"}],
		"nextCursor": "cursor-2"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Search(testutil.OK(results)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/search?q=example&limit=2",
	)

	assert.JSONEq(
		t,
		results,
		response.Body,
	)
}

func TestGateway_CreateArchiveRejectsMissingIdempotencyKey(t *testing.T) {
	upstreams := testutil.StartUpstreams(t)
	gateway := startGateway(t, upstreams)

	response := testutil.Post(
		t,
		gateway,
		"/archives",
		`{"seedUrl":"https://example.com"}`,
		nil,
	)

	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:idempotency-key",
			"title": "Invalid Idempotency Key",
			"status": 400,
			"detail": "Idempotency-Key must be 8 to 200 characters without surrounding whitespace.",
			"instance": "/archives"
		}`,
		response.Body,
	)
}

func TestGateway_GetArchiveForwardsCoordinatorProblem(t *testing.T) {
	problem := `{
		"type": "urn:distributed-web-archive:problem:archive-not-found",
		"title": "Archive Not Found",
		"status": 404,
		"detail": "Archive does not exist.",
		"instance": "/archives/missing"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(
			testutil.Response{
				Status: http.StatusNotFound,
				Body:   problem,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/missing",
	)

	assert.JSONEq(
		t,
		problem,
		response.Body,
	)
}

func TestGateway_GetWACZForwardsPartialContent(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
		testutil.Capture(
			testutil.Response{
				Status: http.StatusPartialContent,
				Headers: map[string]string{
					"Content-Type":  "application/wacz",
					"Content-Range": "bytes 0-9/100",
					"Accept-Ranges": "bytes",
					"ETag":          `"wacz-1"`,
				},
				Body: "wacz-chunk",
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
		map[string]string{
			"Range": "bytes=0-9",
		},
	)

	assert.Equal(
		t,
		http.StatusPartialContent,
		response.Status,
	)
	assert.Equal(
		t,
		"bytes 0-9/100",
		response.Header.Get("Content-Range"),
	)
	assert.Equal(
		t,
		"wacz-chunk",
		response.Body,
	)
}

func TestGateway_CreateSessionReturnsSession(t *testing.T) {
	session := `{
		"sessionId": "session-1",
		"archiveId": "archive-1",
		"status": "ACTIVE",
		"expiresAt": "2026-01-01T00:00:00Z"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Login(
			testutil.Response{
				Status: http.StatusCreated,
				Body:   session,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Post(
		t,
		gateway,
		"/sessions",
		`{"archiveId":"archive-1","targetUrl":"https://example.com"}`,
		map[string]string{
			"Content-Type":    "application/json",
			"Idempotency-Key": "session-key-1",
		},
	)

	assert.JSONEq(
		t,
		`{
			"sessionId": "session-1",
			"archiveId": "archive-1",
			"status": "ACTIVE",
			"expiresAt": "2026-01-01T00:00:00Z",
			"browserUrl": "/sessions/session-1/browser"
		}`,
		response.Body,
	)
}

func TestGateway_CreateArchiveForwardsIdempotencyKey(t *testing.T) {
	accepted := `{
		"archiveId": "archive-1",
		"status": "ACCEPTED",
		"statusUrl": "/archives/archive-1"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(
			testutil.Response{
				Status: http.StatusAccepted,
				Body:   accepted,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Post(
		t,
		gateway,
		"/archives",
		`{"seedUrl":"https://example.com"}`,
		map[string]string{
			"Content-Type":    "application/json",
			"Idempotency-Key": "archive-key-1",
		},
	)

	assert.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)
	assert.Equal(
		t,
		"archive-key-1",
		upstreams.Coordinator.Requests()[0].Headers.Get("Idempotency-Key"),
	)
}

func TestGateway_GetArchiveReportsUpstreamTimeout(t *testing.T) {
	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(
			testutil.Response{
				Body:  `{"archiveId":"archive-1"}`,
				Delay: 1500 * time.Millisecond,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1",
	)

	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:coordinator-unavailable",
			"title": "Coordinator Unavailable",
			"status": 503,
			"detail": "Archive status is temporarily unavailable.",
			"instance": "/archives/archive-1"
		}`,
		response.Body,
	)
}

func TestGateway_GetSnapshotReturnsSnapshot(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`
	snapshot := `{
		"archiveId": "archive-1",
		"snapshotId": "snapshot-1",
		"url": "https://example.com",
		"finalUrl": "https://example.com/",
		"capturedAt": "2026-01-01T00:00:00Z",
		"contentType": "text/html"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
		testutil.Capture(testutil.OK(snapshot)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1/snapshots/snapshot-1",
	)

	assert.JSONEq(
		t,
		snapshot,
		response.Body,
	)
}

func TestGateway_GetSessionReturnsSession(t *testing.T) {
	session := `{
		"sessionId": "session-1",
		"archiveId": "archive-1",
		"status": "ACTIVE",
		"expiresAt": "2026-01-01T00:00:00Z"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Login(testutil.OK(session)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/sessions/session-1",
	)

	assert.JSONEq(
		t,
		`{
			"sessionId": "session-1",
			"archiveId": "archive-1",
			"status": "ACTIVE",
			"expiresAt": "2026-01-01T00:00:00Z",
			"browserUrl": "/sessions/session-1/browser"
		}`,
		response.Body,
	)
}

func TestGateway_PagesForwardsCaptureProblem(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`
	problem := `{
		"type": "urn:distributed-web-archive:problem:page-limit-exceeded",
		"title": "Page Limit Exceeded",
		"status": 422,
		"detail": "Too many pages requested.",
		"instance": "/archives/archive-1/pages"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
		testutil.Capture(
			testutil.Response{
				Status: http.StatusUnprocessableEntity,
				Body:   problem,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1/pages",
	)

	assert.JSONEq(
		t,
		problem,
		response.Body,
	)
}

func TestGateway_SearchRejectsRepeatedParameter(t *testing.T) {
	upstreams := testutil.StartUpstreams(t)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/search?q=one&q=two",
	)

	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:invalid-search",
			"title": "Invalid Search",
			"status": 400,
			"detail": "unknown or repeated search parameter",
			"instance": "/search"
		}`,
		response.Body,
	)
	assert.Empty(t, upstreams.Search.Requests())
}

func TestGateway_HeadWACZReturnsMetadataWithoutBody(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
		testutil.Capture(
			testutil.Response{
				Status: http.StatusOK,
				Headers: map[string]string{
					"Content-Type":  "application/wacz",
					"Accept-Ranges": "bytes",
					"ETag":          `"wacz-1"`,
				},
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Head(
		t,
		gateway,
		"/archives/archive-1/wacz",
		nil,
	)

	assert.Equal(
		t,
		http.StatusOK,
		response.Status,
	)
	assert.Equal(
		t,
		"application/wacz",
		response.Header.Get("Content-Type"),
	)
	assert.Equal(
		t,
		"bytes",
		response.Header.Get("Accept-Ranges"),
	)
	assert.Equal(
		t,
		`"wacz-1"`,
		response.Header.Get("ETag"),
	)
	assert.Empty(t, response.Body)
}

func TestGateway_GetWACZRejectsMultipleRanges(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Send(
		t,
		http.MethodGet,
		gateway,
		"/archives/archive-1/wacz",
		"",
		map[string]string{
			"Range": "bytes=0-1,3-4",
		},
	)

	assert.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)
	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:invalid-range",
			"title": "Invalid Range",
			"status": 400,
			"detail": "Only one valid byte range is supported.",
			"instance": "/archives/archive-1/wacz"
		}`,
		response.Body,
	)
	assert.Empty(t, upstreams.Capture.Requests())
}

func TestGateway_UpdateSessionReturnsUpdatedSession(t *testing.T) {
	session := `{
		"sessionId": "session-1",
		"archiveId": "archive-1",
		"status": "ACTIVE",
		"expiresAt": "2026-01-01T00:00:00Z"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Login(testutil.OK(session)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Put(
		t,
		gateway,
		"/sessions/session-1",
		`{"status":"ACTIVE"}`,
		map[string]string{
			"Content-Type": "application/json",
		},
	)

	assert.JSONEq(
		t,
		`{
			"sessionId": "session-1",
			"archiveId": "archive-1",
			"status": "ACTIVE",
			"expiresAt": "2026-01-01T00:00:00Z",
			"browserUrl": "/sessions/session-1/browser"
		}`,
		response.Body,
	)

	requests := upstreams.Login.Requests()
	require.Len(
		t,
		requests,
		1,
	)
	assert.Equal(
		t,
		http.MethodPut,
		requests[0].Method,
	)
	assert.Equal(
		t,
		"/sessions/session-1",
		requests[0].Path,
	)
	assert.JSONEq(
		t,
		`{"status":"ACTIVE"}`,
		requests[0].Body,
	)
}

func TestGateway_BrowserProxiesActiveSessionToLogin(t *testing.T) {
	session := `{
		"sessionId": "session-1",
		"archiveId": "archive-1",
		"status": "ACTIVE",
		"expiresAt": "2026-01-01T00:00:00Z"
	}`
	page := `<html><body>browser</body></html>`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Login(
			testutil.OK(session),
			testutil.Response{
				Status: http.StatusOK,
				Headers: map[string]string{
					"Content-Type": "text/html",
				},
				Body: page,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/sessions/session-1/browser",
	)

	assert.Equal(
		t,
		page,
		response.Body,
	)

	requests := upstreams.Login.Requests()
	require.Len(
		t,
		requests,
		2,
	)
	assert.Equal(
		t,
		"/sessions/session-1",
		requests[0].Path,
	)
	assert.Equal(
		t,
		"/sessions/session-1/browser",
		requests[1].Path,
	)
}

func TestGateway_BrowserRejectsClosedSession(t *testing.T) {
	session := `{
		"sessionId": "session-1",
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"expiresAt": "2026-01-01T00:00:00Z"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Login(testutil.OK(session)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/sessions/session-1/browser",
	)

	assert.Equal(
		t,
		http.StatusConflict,
		response.Status,
	)
	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:session-closed",
			"title": "Session Closed",
			"status": 409,
			"detail": "The interactive session is no longer available.",
			"instance": "/sessions/session-1/browser"
		}`,
		response.Body,
	)
	assert.Len(
		t,
		upstreams.Login.Requests(),
		1,
	)
}

func TestGateway_GetWACZForwardsUnsatisfiedRange(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`
	problem := `{
		"type": "urn:distributed-web-archive:problem:range-not-satisfiable",
		"title": "Range Not Satisfiable",
		"status": 416,
		"detail": "The requested range is outside the archive."
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
		testutil.Capture(
			testutil.Response{
				Status: http.StatusRequestedRangeNotSatisfiable,
				Headers: map[string]string{
					"Content-Range": "bytes */100",
				},
				Body: problem,
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
		map[string]string{
			"Range": "bytes=200-300",
		},
	)

	assert.Equal(
		t,
		http.StatusRequestedRangeNotSatisfiable,
		response.Status,
	)
	assert.Equal(
		t,
		"bytes */100",
		response.Header.Get("Content-Range"),
	)
	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:range-not-satisfiable",
			"title": "Range Not Satisfiable",
			"status": 416,
			"detail": "The requested range is outside the archive.",
			"instance": "/archives/archive-1/wacz"
		}`,
		response.Body,
	)

	requests := upstreams.Capture.Requests()
	require.Len(
		t,
		requests,
		1,
	)
	assert.Equal(
		t,
		"bytes=200-300",
		requests[0].Headers.Get("Range"),
	)
}

func TestGateway_CreateSessionRejectsMissingIdempotencyKey(t *testing.T) {
	upstreams := testutil.StartUpstreams(t)
	gateway := startGateway(t, upstreams)

	response := testutil.Post(
		t,
		gateway,
		"/sessions",
		`{"archiveId":"archive-1","targetUrl":"https://example.com"}`,
		nil,
	)

	assert.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)
	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:invalid-idempotency-key",
			"title": "Invalid Idempotency Key",
			"status": 400,
			"detail": "Idempotency-Key is required and must contain 8 to 200 characters.",
			"instance": "/sessions"
		}`,
		response.Body,
	)
	assert.Empty(t, upstreams.Login.Requests())
}

func TestGateway_CreateArchiveSetsStatusURL(t *testing.T) {
	accepted := `{
		"archiveId": "archive-1",
		"status": "ACCEPTED",
		"statusUrl": "upstream-status"
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(
			testutil.Response{
				Status: http.StatusAccepted,
				Body:   accepted,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Post(
		t,
		gateway,
		"/archives",
		`{"seedUrl":"https://example.com"}`,
		map[string]string{
			"Content-Type":    "application/json",
			"Idempotency-Key": "archive-key-1",
		},
	)

	assert.Equal(
		t,
		http.StatusAccepted,
		response.Status,
	)
	assert.Equal(
		t,
		"/archives/archive-1",
		response.Header.Get("Location"),
	)
	assert.JSONEq(
		t,
		`{
			"archiveId": "archive-1",
			"status": "ACCEPTED",
			"statusUrl": "/archives/archive-1"
		}`,
		response.Body,
	)
}

func TestGateway_SearchForwardsUpstreamProblem(t *testing.T) {
	problem := `{
		"type": "urn:distributed-web-archive:problem:search-unavailable",
		"title": "Search Unavailable",
		"status": 503,
		"detail": "Search index is rebuilding."
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Search(
			testutil.Response{
				Status: http.StatusServiceUnavailable,
				Body:   problem,
			},
		),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/search?q=example",
	)

	assert.Equal(
		t,
		http.StatusServiceUnavailable,
		response.Status,
	)
	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:search-unavailable",
			"title": "Search Unavailable",
			"status": 503,
			"detail": "Search index is rebuilding.",
			"instance": "/search"
		}`,
		response.Body,
	)
}

func TestGateway_PagesRejectsInvalidPagination(t *testing.T) {
	status := `{
		"archiveId": "archive-1",
		"status": "COMPLETED",
		"decision": "PUBLISH",
		"replay": {"status": "READY"}
	}`

	upstreams := testutil.StartUpstreams(
		t,
		testutil.Coordinator(testutil.OK(status)),
	)
	gateway := startGateway(t, upstreams)

	response := testutil.Get(
		t,
		gateway,
		"/archives/archive-1/pages?limit=many",
	)

	assert.Equal(
		t,
		http.StatusBadRequest,
		response.Status,
	)
	assert.JSONEq(
		t,
		`{
			"type": "urn:distributed-web-archive:problem:invalid-pagination",
			"title": "Invalid Pagination",
			"status": 400,
			"detail": "limit must be an integer",
			"instance": "/archives/archive-1/pages"
		}`,
		response.Body,
	)
	assert.Empty(t, upstreams.Capture.Requests())
}
