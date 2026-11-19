// Package response formats public Gateway HTTP failures.
package response

import (
	"errors"
	"net/http"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/application"
)

func WriteDependencyError(
	w http.ResponseWriter,
	r *http.Request,
	err error,
	service, invalidDetail string,
) {
	var failure *application.DependencyFailure

	if errors.As(err, &failure) {
		if failure.ContentRange != "" && failure.Status == http.StatusRequestedRangeNotSatisfiable {
			w.Header().Set("Content-Range", failure.ContentRange)
		}
		httpx.WriteProblem(w, httpx.Problem{
			Type:     failure.Type,
			Title:    failure.Title,
			Status:   failure.Status,
			Detail:   failure.Detail,
			Instance: r.URL.Path,
		})

		return
	}

	if errors.Is(err, application.ErrInvalidUpstream) {
		httpx.WriteProblem(w, httpx.NewProblem(
			r,
			http.StatusBadGateway,
			"invalid-upstream",
			"Invalid Upstream Response",
			invalidDetail,
		))

		return
	}

	httpx.WriteProblem(w, httpx.NewProblem(
		r,
		http.StatusServiceUnavailable,
		"dependency-unavailable",
		"Dependency Unavailable",
		service+" could not complete the request.",
	))
}
