package httpx_test

import (
	"testing"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/stretchr/testify/assert"
)

func TestValidateIdempotencyKey_AcceptsOpaqueKey(t *testing.T) {
	assert.True(t, httpx.ValidateIdempotencyKey("archive-run-123"))
}

func TestValidateIdempotencyKey_RejectsControlCharacters(t *testing.T) {
	assert.False(t, httpx.ValidateIdempotencyKey("archive\nrun-123"))
}

func TestValidateIdempotencyKey_RejectsOuterWhitespace(t *testing.T) {
	assert.False(t, httpx.ValidateIdempotencyKey(" archive-run-123"))
}

func TestValidateIdempotencyKey_RejectsShortKey(t *testing.T) {
	assert.False(t, httpx.ValidateIdempotencyKey("short"))
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
