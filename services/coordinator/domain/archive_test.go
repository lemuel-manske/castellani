package domain

import (
	"errors"
	"testing"
)

func TestSubmissionValidateAcceptsValidSubmission(t *testing.T) {
	submission := validSubmission()

	err := submission.Validate()

	assertNoError(t, err)
}

func TestSubmissionValidateRejectsInvalidSeedURL(t *testing.T) {
	submission := validSubmission()
	submission.SeedURL = "ftp://example.com"

	err := submission.Validate()

	assertValidationError(t, err, "seedUrl")
}

func TestSubmissionValidateRejectsMissingMaxDepth(t *testing.T) {
	submission := validSubmission()
	submission.MaxDepth = nil

	err := submission.Validate()

	assertValidationError(t, err, "maxDepth")
}

func TestSubmissionValidateRejectsNegativeMaxDepth(t *testing.T) {
	depth := -1
	submission := validSubmission()
	submission.MaxDepth = &depth

	err := submission.Validate()

	assertValidationError(t, err, "maxDepth")
}

func TestSubmissionValidateRejectsMissingMaxPages(t *testing.T) {
	submission := validSubmission()
	submission.MaxPages = nil

	err := submission.Validate()

	assertValidationError(t, err, "maxPages")
}

func TestSubmissionValidateRejectsNonPositiveMaxPages(t *testing.T) {
	pages := 0
	submission := validSubmission()
	submission.MaxPages = &pages

	err := submission.Validate()

	assertValidationError(t, err, "maxPages")
}

func TestSubmissionValidateRejectsNonPositiveAuthGeneration(t *testing.T) {
	generation := 0
	submission := validSubmission()
	submission.AuthGeneration = &generation

	err := submission.Validate()

	assertValidationError(t, err, "authGeneration")
}

func TestSubmissionValidateRejectsInvalidAllowedOrigin(t *testing.T) {
	submission := validSubmission()
	submission.AllowedOrigins = []string{"javascript:alert(1)"}

	err := submission.Validate()

	assertValidationError(t, err, "allowedOrigins")
}

func TestSubmissionValidateRejectsDuplicateAllowedOrigins(t *testing.T) {
	submission := validSubmission()
	submission.AllowedOrigins = []string{
		"https://example.com",
		"https://example.com",
	}

	err := submission.Validate()

	assertValidationError(t, err, "allowedOrigins")
}

func validSubmission() Submission {
	depth := 2
	pages := 25

	return Submission{
		SeedURL:        "https://example.com",
		MaxDepth:       &depth,
		MaxPages:       &pages,
		AllowedOrigins: []string{"https://other.example.com"},
	}
}

func assertValidationError(t *testing.T, err error, field string) {
	t.Helper()

	var validationError ValidationError

	if !errors.As(err, &validationError) {
		t.Fatalf("expected ValidationError, got %v", err)
	}

	if validationError.Field != field {
		t.Fatalf("expected validation field %q, got %q", field, validationError.Field)
	}
}

func assertNoError(t *testing.T, err error) {
	t.Helper()

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}
