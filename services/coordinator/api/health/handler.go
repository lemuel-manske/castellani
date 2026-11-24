// Package healthapi exposes the Coordinator health HTTP endpoints.
package healthapi

import "net/http"

const (
	mediaType = "text/plain; charset=utf-8"

	response = "ok\n"
)

type Handler struct {
	ready func() bool
}

func NewHandler(ready func() bool) Handler {
	return Handler{
		ready: ready,
	}
}

func writeOK(w http.ResponseWriter) {
	w.Header().Set("Content-Type", mediaType)
	w.WriteHeader(http.StatusOK)

	_, _ = w.Write([]byte(response))
}
