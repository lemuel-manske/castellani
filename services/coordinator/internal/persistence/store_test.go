package persistence

import (
	"context"
	"sync"
	"testing"

	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestAdmission_AtomicallyRecordsRunAndStartCommand(t *testing.T) {
	database := newDynamo()
	store := New(database, "")

	accepted, err := admit(store, "unique-key", "digest", "run-1")
	require.NoError(t, err)

	assert.Equal(t, "run-1", accepted.ArchiveID)

	assert.Len(t, database.keys, 1)

	assert.Len(t, database.runs, 1)

	assert.Len(t, database.outbox, 1)

	assert.Equal(t, outboxPending, stringAttr(database.outbox["run-1:start:1"], "state"))
}

func TestAdmission_ConcurrentRetriesProduceOneRun(t *testing.T) {
	database := newDynamo()
	store := New(database, "")

	var workers sync.WaitGroup
	results := make(chan archive.AcceptedResponse, 100)
	failures := make(chan error, 100)

	for range 100 {
		workers.Add(1)

		go func() {
			defer workers.Done()

			accepted, err := admit(store, "same-key", "same-digest", "run-1")
			results <- accepted
			failures <- err
		}()
	}

	workers.Wait()
	close(results)
	close(failures)

	for err := range failures {
		require.NoError(t, err)
	}

	for accepted := range results {
		assert.Equal(t, "run-1", accepted.ArchiveID)
	}

	assert.Len(t, database.keys, 1)

	assert.Len(t, database.runs, 1)

	assert.Len(t, database.outbox, 1)
}

func TestAdmission_ChangingRequestUnderExistingKeyIsRejected(t *testing.T) {
	database := newDynamo()
	store := New(database, "")

	_, err := admit(store, "same-key", "first", "run-1")
	require.NoError(t, err)

	_, err = admit(store, "same-key", "second", "run-2")

	require.ErrorIs(t, err, application.ErrConflict)


	assert.Len(t, database.runs, 1)

	assert.Len(t, database.outbox, 1)
}

func TestArchive_AdmittedRunHasReadableInitialStatus(t *testing.T) {
	database := newDynamo()
	store := New(database, "")

	_, err := admit(store, "unique-key", "digest", "run-1")
	require.NoError(t, err)

	status, err := store.Status(context.Background(), "run-1")
	require.NoError(t, err)

	assert.Equal(t, "run-1", status.ArchiveID)

	assert.Equal(t, archive.Accepted, status.Status)

	assert.Equal(t, "NOT_READY", status.Replay.Status)

	assert.Equal(t, "PENDING", status.Search.Status)
}
