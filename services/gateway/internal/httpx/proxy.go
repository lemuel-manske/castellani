package httpx

import (
	"encoding/json"
	"errors"
	"net/http"

	sharedhttp "github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

func ForwardJSON(w http.ResponseWriter, r *http.Request, result upstream.Result, success int, unavailable string) {
	if result.Status == success {
		var body any

		if err := json.Unmarshal(result.Body, &body); err != nil || body == nil {
			responseProblem := sharedhttp.NewProblem(
				r,
				http.StatusBadGateway,
				"invalid-upstream",
				"Invalid Upstream Response",
				"Upstream returned invalid JSON.",
			)
			sharedhttp.WriteProblem(w, responseProblem)
			return
		}

		w.Header().Set(sharedhttp.HeaderContentType, sharedhttp.MediaTypeJSON)
		w.Header().Set(sharedhttp.HeaderCacheControl, sharedhttp.CacheNoStore)
		w.WriteHeader(success)
		_, _ = w.Write(result.Body)
		return
	}

	var problem sharedhttp.Problem
	problemError := json.Unmarshal(result.Body, &problem)
	validProblem := problemError == nil && problem.Type != "" && problem.Title != "" &&
		problem.Status == result.Status

	if validProblem && allowedFailure(result.Status) {
		problem.Instance = r.URL.Path
		sharedhttp.WriteProblem(w, problem)
		return
	}

	responseProblem := sharedhttp.NewProblem(
		r,
		http.StatusBadGateway,
		"invalid-upstream",
		"Invalid Upstream Response",
		"Upstream returned an unexpected response.",
	)
	sharedhttp.WriteProblem(w, responseProblem)
}

func allowedFailure(status int) bool {
	switch status {
	case http.StatusBadRequest, http.StatusUnauthorized, http.StatusForbidden, http.StatusNotFound,
		http.StatusConflict, http.StatusUnprocessableEntity, http.StatusServiceUnavailable:
		return true
	default:
		return false
	}
}

func UpstreamError(w http.ResponseWriter, r *http.Request, err error, service string) {
	status := http.StatusServiceUnavailable
	kind := "dependency-unavailable"
	title := "Dependency Unavailable"

	if errors.Is(err, upstream.ErrInvalidResponse) {
		status = http.StatusBadGateway
		kind = "invalid-upstream"
		title = "Invalid Upstream Response"
	}

	responseProblem := sharedhttp.NewProblem(
		r,
		status,
		kind,
		title,
		service+" could not complete the request.",
	)
	sharedhttp.WriteProblem(w, responseProblem)
}
