// Package httpx provides HTTP protocol conventions shared by the Go services.
package httpx

import (
	"encoding/json"
	"net/http"
)

const (
	MediaTypeProblem = "application/problem+json"

	ProblemTypePrefix = "urn:distributed-web-archive:problem:"
)

type Problem struct {
	Type     string `json:"type"`
	Title    string `json:"title"`
	Status   int    `json:"status"`
	Detail   string `json:"detail,omitempty"`
	Instance string `json:"instance,omitempty"`
}

func NewProblem(
	r *http.Request,
	status int,
	kind, title, detail string,
) Problem {
	return Problem{
		Type:     ProblemTypePrefix + kind,
		Title:    title,
		Status:   status,
		Detail:   detail,
		Instance: r.URL.Path,
	}
}

func WriteProblem(w http.ResponseWriter, problem Problem) {
	w.Header().Set(HeaderContentType, MediaTypeProblem)
	w.Header().Set(HeaderCacheControl, CacheNoStore)

	w.WriteHeader(problem.Status)
	_ = json.NewEncoder(w).Encode(problem)
}
