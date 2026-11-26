package domain

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSubmission_ValidateAcceptsValidSubmission(t *testing.T) {
	maxDepth := 2
	maxPages := 5

	authGeneration := 1

	submission := Submission{
		SeedURL:        "https://example.org/",
		MaxDepth:       &maxDepth,
		MaxPages:       &maxPages,
		AllowedOrigins: []string{"https://example.org/"},
		AuthGeneration: &authGeneration,
	}

	require.NoError(t, submission.Validate())
}

func TestSubmission_ValidateRejectsNegativeMaxDepth(t *testing.T) {
	maxDepth := -1
	maxPages := 5

	submission := Submission{
		SeedURL:  "https://example.org/",
		MaxDepth: &maxDepth,
		MaxPages: &maxPages,
	}

	err := submission.Validate()

	var actual ValidationError
	require.ErrorAs(
		t,
		err,
		&actual,
	)

	assert.Equal(
		t,
		ValidationError{
			Field:   "maxDepth",
			Message: "must be a nonnegative integer",
		},
		actual,
	)
}

func TestSubmission_ValidateRejectsDuplicateAllowedOrigins(t *testing.T) {
	maxDepth := 2
	maxPages := 5

	submission := Submission{
		SeedURL:        "https://example.org/",
		MaxDepth:       &maxDepth,
		MaxPages:       &maxPages,
		AllowedOrigins: []string{"https://example.org/", "https://example.org/"},
	}

	err := submission.Validate()

	var actual ValidationError
	require.ErrorAs(
		t,
		err,
		&actual,
	)

	assert.Equal(
		t,
		ValidationError{
			Field:   "allowedOrigins",
			Message: "entries must be unique",
		},
		actual,
	)
}

func TestSubmission_FingerprintIgnoresAllowedOriginOrder(t *testing.T) {
	maxDepth := 2
	maxPages := 5

	first := Submission{
		SeedURL:        "https://example.org/",
		MaxDepth:       &maxDepth,
		MaxPages:       &maxPages,
		AllowedOrigins: []string{"https://b.example/", "https://a.example/"},
	}

	second := Submission{
		SeedURL:        "https://example.org/",
		MaxDepth:       &maxDepth,
		MaxPages:       &maxPages,
		AllowedOrigins: []string{"https://a.example/", "https://b.example/"},
	}

	firstFingerprint, err := first.Fingerprint()
	require.NoError(t, err)

	secondFingerprint, err := second.Fingerprint()
	require.NoError(t, err)

	assert.Equal(
		t,
		firstFingerprint,
		secondFingerprint,
	)
}

func TestSubmission_FingerprintRejectsMissingLimits(t *testing.T) {
	maxPages := 5

	submission := Submission{
		SeedURL:  "https://example.org/",
		MaxPages: &maxPages,
	}

	_, err := submission.Fingerprint()

	require.Error(t, err)
}
