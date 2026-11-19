package archiveapi

import (
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/common"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

const (
	maxRangeHeaderBytes = 256
)

type WACZHandler struct {
	client *upstream.Client
}

func NewWACZHandler(client *upstream.Client) WACZHandler {
	return WACZHandler{client: client}
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
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-archive-id",
			"Invalid Archive ID",
			"Invalid archive ID.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	byteRange := r.Header.Get("Range")
	ifRange := r.Header.Get("If-Range")

	invalidRange := len(byteRange) > maxRangeHeaderBytes || strings.ContainsAny(byteRange, "\r\n,")
	invalidIfRange := len(ifRange) > maxRangeHeaderBytes || strings.ContainsAny(ifRange, "\r\n")

	if invalidRange || invalidIfRange {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-range",
			"Invalid Range",
			"Only one valid byte range is supported.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	path := common.ArchivePathPrefix + url.PathEscape(id) + common.WACZPathSuffix
	response, err := h.client.Stream(r.Context(), r.Method, path, byteRange, ifRange)

	if err != nil {
		common.UpstreamError(w, r, err, "Capture")
		return
	}

	defer response.Body.Close()

	if response.StatusCode == http.StatusNotFound ||
		response.StatusCode == http.StatusServiceUnavailable ||
		response.StatusCode == http.StatusRequestedRangeNotSatisfiable {
		h.writeFailure(w, r, response)
		return
	}

	isSuccess := response.StatusCode == http.StatusOK || response.StatusCode == http.StatusPartialContent

	if !isSuccess || response.Header.Get("Content-Type") != httpx.WACZMediaType {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadGateway,
			"invalid-upstream",
			"Invalid Upstream Response",
			"Capture returned unexpected WACZ metadata.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	for _, header := range []string{"Accept-Ranges", "Content-Range", "ETag", "Last-Modified", "Content-Length"} {
		value := response.Header.Get(header)

		if value != "" {
			w.Header().Set(header, value)
		}
	}

	w.Header().Set("Content-Type", httpx.WACZMediaType)
	w.Header().Set("Cache-Control", "private, no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(response.StatusCode)

	if r.Method == http.MethodHead {
		return
	}

	// Stream directly; never buffer published WACZ objects in Gateway memory.
	_, _ = io.Copy(w, response.Body)
}

func (h WACZHandler) writeFailure(w http.ResponseWriter, r *http.Request, response *http.Response) {
	data, err := io.ReadAll(io.LimitReader(response.Body, httpx.MaxJSONRequestBytes+1))

	if err != nil || len(data) > httpx.MaxJSONRequestBytes {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadGateway,
			"invalid-upstream",
			"Invalid Upstream Response",
			"Capture returned invalid WACZ error metadata.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	var problem httpx.Problem
	decodeErr := json.Unmarshal(data, &problem)
	validProblem := decodeErr == nil && problem.Status == response.StatusCode &&
		problem.Title != "" && problem.Type != ""

	if !validProblem {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadGateway,
			"invalid-upstream",
			"Invalid Upstream Response",
			"Capture returned invalid WACZ error metadata.",
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	if response.StatusCode == http.StatusRequestedRangeNotSatisfiable {
		contentRange := response.Header.Get("Content-Range")

		if contentRange != "" {
			w.Header().Set("Content-Range", contentRange)
		}
	}

	problem.Instance = r.URL.Path
	httpx.WriteProblem(w, problem)
}
