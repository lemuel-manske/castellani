package httpx_test

import (
	"testing"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/stretchr/testify/assert"
)

func TestValidIdempotencyKey_AcceptsOpaqueKey(t *testing.T) {
	assert.True(t, httpx.ValidIdempotencyKey("archive-run-123"))
}

func TestValidIdempotencyKey_RejectsControlCharacters(t *testing.T) {
	assert.False(t, httpx.ValidIdempotencyKey("archive\nrun-123"))
}

func TestValidIdempotencyKey_RejectsOuterWhitespace(t *testing.T) {
	assert.False(t, httpx.ValidIdempotencyKey(" archive-run-123"))
}

func TestValidIdempotencyKey_RejectsShortKey(t *testing.T) {
	assert.False(t, httpx.ValidIdempotencyKey("short"))
}

func TestValidPathSegment_RejectsReservedSegments(t *testing.T) {
	assert.False(t, httpx.ValidPathSegment(".."))
}

func TestValidPathSegment_RejectsSeparators(t *testing.T) {
	assert.False(t, httpx.ValidPathSegment("a/b"))
}

func TestValidPathSegment_AcceptsNormalIdentifier(t *testing.T) {
	assert.True(t, httpx.ValidPathSegment("archive_123"))
}

func TestValidHTTPURL_AcceptsSecureOrigin(t *testing.T) {
	assert.True(t, httpx.ValidHTTPURL("https://example.com/path"))
}

func TestValidHTTPURL_RejectsCredentials(t *testing.T) {
	assert.False(t, httpx.ValidHTTPURL("https://user:secret@example.com/"))
}

func TestValidHTTPURL_RejectsNonHTTPURL(t *testing.T) {
	assert.False(t, httpx.ValidHTTPURL("file:///etc/passwd"))
}
