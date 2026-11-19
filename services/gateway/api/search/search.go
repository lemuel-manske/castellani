// Package searchapi provides HTTP handlers for the Searching API.
package searchapi

import (
	"net/http"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/api/params"
	"github.com/lemuel-manske/unnamed/services/gateway/api/response"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
)

type Handler struct {
	app application.Application
}

func NewHandler(app application.Application) Handler {
	return Handler{
		app: app,
	}
}

func (h Handler) Search(w http.ResponseWriter, r *http.Request) {
	query, err := params.Search(r.URL.Query())

	if err != nil {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadRequest,
			"invalid-search",
			"Invalid Search",
			err.Error(),
		))

		return
	}

	result, err := h.app.Search(r.Context(), query)

	if err != nil {
		response.WriteDependencyError(
			w,
			r,
			err,
			"Search",
			"Search returned invalid results.",
		)

		return
	}

	httpx.JSON(
		w,
		http.StatusOK,
		result,
	)
}
