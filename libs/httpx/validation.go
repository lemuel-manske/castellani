package httpx

import (
	"net/url"
	"strings"
)

const (
	minIdempotencyKeyLength = 8
	maxIdempotencyKeyLength = 200
)

func ValidIdempotencyKey(key string) bool {
	validLength := len(key) >= minIdempotencyKeyLength && len(key) <= maxIdempotencyKeyLength
	cleanWhitespace := strings.TrimSpace(key) == key
	noControlCharacters := !strings.ContainsAny(key, "\r\n\x00")

	return validLength && cleanWhitespace && noControlCharacters
}

func ValidPathSegment(id string) bool {
	reserved := id == "" || id == "." || id == ".."
	forbidden := strings.ContainsAny(id, "/\\?#")

	return !reserved && !forbidden
}

func ValidHTTPURL(raw string) bool {
	target, err := url.Parse(raw)

	if err != nil {
		return false
	}

	httpScheme := target.Scheme == "http" || target.Scheme == "https"
	hasHostname := target.Hostname() != ""
	noCredentials := target.User == nil
	noFragment := target.Fragment == ""

	return httpScheme && hasHostname && noCredentials && noFragment
}
