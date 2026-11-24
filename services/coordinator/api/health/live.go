package healthapi

import "net/http"

func (h Handler) Live(w http.ResponseWriter, _ *http.Request) {
	writeOK(w)
}
