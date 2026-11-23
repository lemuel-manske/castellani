package archiveapi

import (
	"io"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/castellani/services/gateway/api/response"
	"github.com/lemuel-manske/castellani/services/gateway/application"
	"github.com/lemuel-manske/castellani/services/gateway/common"
)

const maxRangeHeaderBytes = 256

type WACZHandler struct {
	app application.Application
}

func NewWACZHandler(app application.Application) WACZHandler {
	return WACZHandler{app: app}
}

func (h WACZHandler) Get(w http.ResponseWriter, r *http.Request) {
	h.deliver(w, r)
}

func (h WACZHandler) Head(w http.ResponseWriter, r *http.Request) {
	h.deliver(w, r)
}

func (h WACZHandler) deliver(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, common.ArchiveIDParameter)

	if !httpx.ValidPathSegment(id) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-archive-id",
			"Invalid Archive ID",
			"Invalid archive ID.",
		))
		return
	}

	rangeHeader := r.Header.Get("Range")
	ifRange := r.Header.Get("If-Range")

	if len(rangeHeader) > maxRangeHeaderBytes ||
		strings.ContainsAny(rangeHeader, "\r\n,") ||
		len(ifRange) > maxRangeHeaderBytes ||
		strings.ContainsAny(ifRange, "\r\n") {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-range",
			"Invalid Range",
			"Only one valid byte range is supported.",
		))
		return
	}

	options := application.WACZOptions{
		MetadataOnly: r.Method == http.MethodHead,
		Range:        rangeHeader,
		IfRange:      ifRange,
	}

	result, err := h.app.GetWACZ(r.Context(), id, options)

	if err != nil {
		response.WriteDependencyError(w, r, err, "Capture", "Capture returned unexpected WACZ metadata.")
		return
	}

	defer result.Body.Close()

	for name, value := range map[string]string{
		"Accept-Ranges":  result.AcceptRanges,
		"Content-Range":  result.ContentRange,
		"ETag":           result.ETag,
		"Last-Modified":  result.LastModified,
		"Content-Length": result.ContentLength,
	} {
		if value != "" {
			w.Header().Set(name, value)
		}
	}

	w.Header().Set(httpx.HeaderContentType, httpx.WACZMediaType)
	w.Header().Set("Cache-Control", "private, no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")

	status := http.StatusOK
	if result.Partial {
		status = http.StatusPartialContent
	}

	w.WriteHeader(status)

	if options.MetadataOnly {
		return
	}

	_, _ = io.Copy(w, result.Body)
}
