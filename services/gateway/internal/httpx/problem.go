package httpx

import (
	"encoding/json"
	"net/http"
)

const (
	HeaderContentType = "Content-Type"
	HeaderCacheControl = "Cache-Control"
	MediaTypeProblem = "application/problem+json"
	MediaTypeJSON = "application/json"
	CacheNoStore = "no-store"
	ProblemTypePrefix = "urn:distributed-web-archive:problem:"
)

type Problem struct {
	Type     string `json:"type"`
	Title    string `json:"title"`
	Status   int    `json:"status"`
	Detail   string `json:"detail,omitempty"`
	Instance string `json:"instance,omitempty"`
}

func WriteProblem(w http.ResponseWriter, r *http.Request, status int, kind, title, detail string) {
	Write(w, Problem{
		Type:     ProblemTypePrefix + kind,
		Title:    title,
		Status:   status,
		Detail:   detail,
		Instance: r.URL.Path,
	})
}

func Write(w http.ResponseWriter, p Problem) {
	w.Header().Set(HeaderContentType, MediaTypeProblem)
	w.Header().Set(HeaderCacheControl, CacheNoStore)
	w.WriteHeader(p.Status)
	_ = json.NewEncoder(w).Encode(p)
}

func JSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set(HeaderContentType, MediaTypeJSON)
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
