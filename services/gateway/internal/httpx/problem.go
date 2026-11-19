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

func WriteProblem(w http.ResponseWriter, r *http.Request, status int, kind, title, detail string) {
	shared.WriteProblem(w, r, status, kind, title, detail)
}

func Write(w http.ResponseWriter, p Problem) {
	shared.Write(w, p)
}

func JSON(w http.ResponseWriter, status int, body any) {
	shared.JSON(w, status, body)
}
