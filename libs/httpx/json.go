package httpx

import (
	"encoding/json"
	"net/http"
)

const MediaTypeJSON = "application/json"

func JSON(
	w http.ResponseWriter,
	status int,
	body any,
) {
	w.Header().Set(HeaderContentType, MediaTypeJSON)
	w.Header().Set(HeaderCacheControl, CacheNoStore)
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
