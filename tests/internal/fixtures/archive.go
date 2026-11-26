// Package fixtures provides request bodies and expected responses for the end-to-end suite.
package fixtures

import (
	"net/http"

	"github.com/lemuel-manske/castellani/tests/internal/contracts"
)

const (
	ValidArchive     = `{"seedUrl":"https://example.com","maxDepth":1,"maxPages":10}`
	MalformedArchive = `{"seedUrl":`
	InvalidArchive   = `{"seedUrl":"https://example.com","maxDepth":-1,"maxPages":10}`
)

const (
	AcceptedIdempotencyKey               = "archive-accepted-0001"
	ShortIdempotencyKey                  = "short"
	UnsupportedContentTypeIdempotencyKey = "archive-content-type-0001"
	MalformedJSONIdempotencyKey          = "archive-malformed-0001"
	InvalidSubmissionIdempotencyKey      = "archive-invalid-0001"
)

func InvalidIdempotencyKeyProblem() contracts.Problem {
	return contracts.Problem{
		Type:     "urn:distributed-web-archive:problem:idempotency-key",
		Title:    "Invalid Idempotency Key",
		Status:   http.StatusBadRequest,
		Detail:   "Idempotency-Key must be 8 to 200 characters without surrounding whitespace.",
		Instance: "/archives",
	}
}

func InvalidContentTypeProblem() contracts.Problem {
	return contracts.Problem{
		Type:     "urn:distributed-web-archive:problem:content-type",
		Title:    "Invalid Content Type",
		Status:   http.StatusBadRequest,
		Detail:   "Expected application/json.",
		Instance: "/archives",
	}
}

func InvalidJSONProblem() contracts.Problem {
	return contracts.Problem{
		Type:     "urn:distributed-web-archive:problem:invalid-json",
		Title:    "Invalid Request",
		Status:   http.StatusBadRequest,
		Detail:   "Expected a valid archive JSON object.",
		Instance: "/archives",
	}
}

func InvalidArchiveProblem() contracts.Problem {
	return contracts.Problem{
		Type:     "urn:distributed-web-archive:problem:invalid-archive",
		Title:    "Invalid Archive",
		Status:   http.StatusUnprocessableEntity,
		Detail:   "maxDepth must be a nonnegative integer",
		Instance: "/archives",
	}
}
