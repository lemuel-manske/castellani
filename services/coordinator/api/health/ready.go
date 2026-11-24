package healthapi

import "net/http"

func (h Handler) Ready(w http.ResponseWriter, _ *http.Request) {
	if !h.ready() {
		http.Error(
			w,
			"unavailable",
			http.StatusServiceUnavailable,
		)

		return
	}

	writeOK(w)
}
