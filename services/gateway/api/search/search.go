package searchapi

import (
	"net/http"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/common"
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
	if err := common.ValidateSearch(r.URL.Query()); err != nil {
		responseProblem := httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-search",
			"Invalid Search",
			err.Error(),
		)
		httpx.WriteProblem(w, responseProblem)
		return
	}

	result, err := h.client.JSON(r.Context(), http.MethodGet, Path, r.URL.RawQuery, "", nil)

	if err != nil {
		common.UpstreamError(w, r, err, "Search")
		return
	}

	common.ForwardJSON(w, r, result, http.StatusOK, "Search")
}
