package coordinatortest

import (
	"context"
	"sync"
	"time"

	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

// Archives records admitted archives for isolated HTTP behavior tests.
// It does not model DynamoDB transaction semantics.
type Archives struct {
	mu       sync.Mutex
	byKey    map[string]admission
	byID     map[string]archive.Status
	admitted int
}

type admission struct {
	digest   string
	accepted archive.AcceptedResponse
}

func NewArchives() *Archives {
	return &Archives{
		byKey: make(map[string]admission),
		byID:  make(map[string]archive.Status),
	}
}

func (a *Archives) Admit(_ context.Context, key, digest string, accepted archive.AcceptedResponse, _ archive.Submission, _ time.Time) (archive.AcceptedResponse, error) {
	a.mu.Lock()
	defer a.mu.Unlock()

	if previous, exists := a.byKey[key]; exists {
		if previous.digest != digest {
			return archive.AcceptedResponse{}, application.ErrConflict
		}

		return previous.accepted, nil
	}

	a.admitted++
	a.byKey[key] = admission{digest: digest, accepted: accepted}
	a.byID[accepted.ArchiveID] = archive.Status{
		ArchiveID: accepted.ArchiveID,
		Status:    archive.Accepted,
		Replay:    archive.Replay{Status: "NOT_READY"},
		Search:    archive.Search{Status: "PENDING"},
	}

	return accepted, nil
}

func (a *Archives) Status(_ context.Context, id string) (archive.Status, error) {
	a.mu.Lock()
	defer a.mu.Unlock()

	record, exists := a.byID[id]

	if !exists {
		return archive.Status{}, application.ErrNotFound
	}

	return record, nil
}

func (a *Archives) AdmissionCount() int {
	a.mu.Lock()
	defer a.mu.Unlock()

	return a.admitted
}
