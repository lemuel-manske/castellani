package searchapi

import (
	sharedhttp "github.com/lemuel-manske/castellani/libs/httpx"
	"net/http"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

const Path = "/search"

type Handler struct {
	client *upstream.Client
}

func NewHandler(client *upstream.Client) Handler {
	return Handler{client: client}
}

func (h Handler) Search(w http.ResponseWriter, r *http.Request) {
	if err := httpx.ValidateSearch(r.URL.Query()); err != nil {
		responseProblem := sharedhttp.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-search",
			"Invalid Search",
			err.Error(),
		)
		sharedhttp.WriteProblem(w, responseProblem)
		return
	}

	result, err := h.client.JSON(r.Context(), http.MethodGet, Path, r.URL.RawQuery, "", nil)

	if err != nil {
		httpx.UpstreamError(w, r, err, "Search")
		return
	}

	httpx.ForwardJSON(w, r, result, http.StatusOK, "Search")
}
