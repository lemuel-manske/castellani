package application

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/services/coordinator/domain"
	"github.com/lemuel-manske/castellani/services/coordinator/persistence"
)

type archiveRepositoryStub struct{}

func (archiveRepositoryStub) Admit(context.Context, persistence.Admission) (persistence.AcceptedArchive, error) {
	return persistence.AcceptedArchive{}, nil
}

func (archiveRepositoryStub) Find(context.Context, string) (domain.Archive, error) {
	return domain.Archive{}, nil
}

func (archiveRepositoryStub) CommitEvent(
	context.Context,
	domain.Archive,
	domain.Archive,
	domain.Event,
	[]domain.Effect,
) error {
	return nil
}

func (archiveRepositoryStub) ListStalled(context.Context, time.Time, int) ([]domain.Archive, error) {
	return nil, nil
}

func (archiveRepositoryStub) ScheduleRecovery(context.Context, domain.Archive, domain.Effect) error {
	return nil
}

func TestSubmitArchiveReturnsDomainValidationError(t *testing.T) {
	app := NewApplication(archiveRepositoryStub{})

	_, err := app.SubmitArchive(
		context.Background(),
		"valid-idempotency-key",
		domain.Submission{},
	)

	assertInvalidSubmission(t, err)
	assertValidationDetail(t, err, "seedUrl must be an absolute HTTP(S) URL without credentials or fragment")
}

func assertInvalidSubmission(t *testing.T, err error) {
	t.Helper()

	if !errors.Is(err, ErrInvalidSubmission) {
		t.Fatalf("expected ErrInvalidSubmission, got %v", err)
	}
}

func assertValidationDetail(t *testing.T, err error, expected string) {
	t.Helper()

	if err == nil {
		t.Fatal("expected validation error")
	}

	if err.Error() != expected {
		t.Fatalf("expected validation detail %q, got %q", expected, err.Error())
	}
}
