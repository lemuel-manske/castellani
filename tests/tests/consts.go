package tests

import "time"

const (
	ContentTypeJSON    = "application/json"
	ContentTypeProblem = "application/problem+json"

	HeaderContentType    = "Content-Type"
	HeaderIdempotencyKey = "Idempotency-Key"
	HeaderLocation       = "Location"

	ArchiveTimeout = 90 * time.Second
	ZipPrefix      = "\x50\x4b\x03\x04"
)
