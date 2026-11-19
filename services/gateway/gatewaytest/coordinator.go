package gatewaytest

import (
	"io"
	"net/http"
	"sync/atomic"

	"github.com/lemuel-manske/castellani/libs/httpx"
)

func AcceptArchive(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	w.WriteHeader(http.StatusAccepted)
	_, _ = io.WriteString(w, AcceptedArchive)
}

func ReturnArchiveStatus(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeJSON)
	_, _ = io.WriteString(w, RunningArchive)
}

func RejectConflictingKey(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set(httpx.HeaderContentType, httpx.MediaTypeProblem)
	w.WriteHeader(http.StatusConflict)
	_, _ = io.WriteString(w, `{"type":"urn:coordinator:idempotency-conflict","title":"Conflict","status":409,"detail":"Key was used for different content."}`)
}

func Disconnect(http.ResponseWriter, *http.Request) {
	panic(http.ErrAbortHandler)
}

func ReturnMalformedAdmission(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusAccepted)
	_, _ = io.WriteString(w, `{"archiveId":"","status":"ACCEPTED"}`)
}

func ReturnMismatchedArchive(w http.ResponseWriter, _ *http.Request) {
	_, _ = io.WriteString(w, `{"archiveId":"different-run","status":"RUNNING","capture":{},"replay":{},"search":{}}`)
}

func Unused(http.ResponseWriter, *http.Request) {}

type RecordingCoordinator struct {
	requests atomic.Int32
}

func (c *RecordingCoordinator) Accept(w http.ResponseWriter, r *http.Request) {
	c.requests.Add(1)
	AcceptArchive(w, r)
}

func (c *RecordingCoordinator) CallCount() int32 {
	return c.requests.Load()
}
