package archiveapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/castellani/services/coordinator/application"
	"github.com/lemuel-manske/castellani/services/coordinator/domain"
	"github.com/lemuel-manske/castellani/services/coordinator/persistence"
)

type repositoryStub struct{}

func (repositoryStub) Admit(context.Context, persistence.Admission) (persistence.AcceptedArchive, error) {
	return persistence.AcceptedArchive{}, nil
}

func (repositoryStub) Find(context.Context, string) (domain.Archive, error) {
	return domain.Archive{}, nil
}

func (repositoryStub) CommitEvent(
	context.Context,
	domain.Archive,
	domain.Archive,
	domain.Event,
	[]domain.Effect,
) error {
	return nil
}

func (repositoryStub) ListStalled(context.Context, time.Time, int) ([]domain.Archive, error) {
	return nil, nil
}

func (repositoryStub) ScheduleRecovery(context.Context, domain.Archive, domain.Effect) error {
	return nil
}

func TestWriteFailureReturnsProblemDetailsForInvalidSubmission(t *testing.T) {
	app := application.NewApplication(repositoryStub{})

	_, err := app.SubmitArchive(
		context.Background(),
		"valid-idempotency-key",
		domain.Submission{},
	)

	response := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodPost, "/archives", nil)

	writeFailure(response, request, err)

	assertProblemResponse(t, response, http.StatusUnprocessableEntity)
}

func assertProblemResponse(t *testing.T, response *httptest.ResponseRecorder, status int) {
	t.Helper()

	if response.Code != status {
		t.Fatalf("expected status %d, got %d", status, response.Code)
	}

	if response.Header().Get(httpx.HeaderContentType) != httpx.MediaTypeProblem {
		t.Fatalf("expected Content-Type %q, got %q", httpx.MediaTypeProblem, response.Header().Get(httpx.HeaderContentType))
	}

	var problem httpx.Problem

	if err := json.Unmarshal(response.Body.Bytes(), &problem); err != nil {
		t.Fatalf("decode Problem Details response: %v", err)
	}

	if problem.Status != status {
		t.Fatalf("expected problem status %d, got %d", status, problem.Status)
	}

	if problem.Type != httpx.ProblemTypePrefix+"invalid-archive" {
		t.Fatalf("unexpected problem type %q", problem.Type)
	}

	if problem.Title != "Invalid Archive" {
		t.Fatalf("unexpected problem title %q", problem.Title)
	}

	if problem.Detail != "seedUrl must be an absolute HTTP(S) URL without credentials or fragment" {
		t.Fatalf("unexpected problem detail %q", problem.Detail)
	}
}
