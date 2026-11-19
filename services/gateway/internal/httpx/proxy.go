package httpx

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/lemuel-manske/unnamed/services/gateway/internal/upstream"
)

func ForwardJSON(w http.ResponseWriter, r *http.Request, result upstream.Result, success int, unavailable string) {
	if result.Status == success {
		var body any

		if err := json.Unmarshal(result.Body, &body); err != nil || body == nil {
			WriteProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Upstream returned invalid JSON.")
			return
		}

		w.Header().Set(HeaderContentType, MediaTypeJSON)
		w.Header().Set(HeaderCacheControl, CacheNoStore)
		w.WriteHeader(success)
		_, _ = w.Write(result.Body)
		return
	}

	var problem Problem
	problemError := json.Unmarshal(result.Body, &problem)
	validProblem := problemError == nil && problem.Type != "" && problem.Title != "" &&
		problem.Status == result.Status

	if validProblem && allowedFailure(result.Status) {
		problem.Instance = r.URL.Path
		Write(w, problem)
		return
	}

	WriteProblem(w, r, http.StatusBadGateway, "invalid-upstream", "Invalid Upstream Response", "Upstream returned an unexpected response.")
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

	WriteProblem(w, r, status, kind, title, service+" could not complete the request.")
}
