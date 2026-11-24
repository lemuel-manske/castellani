package sessionapi

import (
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/castellani/services/gateway/api/response"
	"github.com/lemuel-manske/castellani/services/gateway/application"
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

var closedSessionStatuses = map[string]struct{}{
	"COMPLETED": {},
	"CANCELLED": {},
	"FAILED":    {},
	"EXPIRED":   {},
}

type BrowserHandler struct {
	app   application.Application
	proxy *httputil.ReverseProxy
}

func NewBrowserHandler(app application.Application, loginOrigin url.URL) BrowserHandler {
	proxy := httputil.NewSingleHostReverseProxy(&loginOrigin)
	proxy.FlushInterval = -1
	proxy.Rewrite = func(request *httputil.ProxyRequest) {
		request.SetURL(&loginOrigin)
		request.Out.Host = loginOrigin.Host
	}

	return BrowserHandler{
		app:   app,
		proxy: proxy,
	}
}

func (h BrowserHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, common.SessionIDParameter)

	if !httpx.ValidPathSegment(id) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-session-id",
			"Invalid Session ID",
			"Invalid session ID.",
		))

		return
	}

	session, err := h.app.GetSession(r.Context(), id)

	if err != nil {
		response.WriteDependencyError(
			w,
			r,
			err,
			"Capture login manager",
			"Capture login manager returned invalid session metadata.",
		)

		return
	}

	if _, closed := closedSessionStatuses[session.Status]; closed {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusConflict,
			"session-closed",
			"Session Closed",
			"The interactive session is no longer available.",
		))

		return
	}

	h.proxy.ServeHTTP(w, r)
}
