package httpx

import (
	"net/http"

	shared "github.com/lemuel-manske/castellani/libs/httpx"
)

const (
	HeaderContentType  = shared.HeaderContentType
	HeaderCacheControl = shared.HeaderCacheControl
	MediaTypeProblem   = shared.MediaTypeProblem
	MediaTypeJSON      = shared.MediaTypeJSON
	CacheNoStore       = shared.CacheNoStore
	ProblemTypePrefix = shared.ProblemTypePrefix
)

type Problem = shared.Problem

func NewProblem(r *http.Request, status int, kind, title, detail string) Problem {
	return shared.NewProblem(r, status, kind, title, detail)
}

func WriteProblem(w http.ResponseWriter, problem Problem) {
	shared.WriteProblem(w, problem)
}

func JSON(w http.ResponseWriter, status int, body any) {
	shared.JSON(w, status, body)
}
