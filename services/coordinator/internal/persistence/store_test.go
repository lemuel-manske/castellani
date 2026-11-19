package persistence

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type recordingDynamo struct {
	mu     sync.Mutex
	keys   map[string]map[string]types.AttributeValue
	runs   map[string]map[string]types.AttributeValue
	outbox map[string]map[string]types.AttributeValue
}

func newDynamo() *recordingDynamo {
	return &recordingDynamo{keys: map[string]map[string]types.AttributeValue{}, runs: map[string]map[string]types.AttributeValue{}, outbox: map[string]map[string]types.AttributeValue{}}
}
func (d *recordingDynamo) TransactWriteItems(_ context.Context, in *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	key := stringAttr(in.TransactItems[0].Put.Item, "idempotencyKey")
	if _, ok := d.keys[key]; ok {
		return nil, &types.TransactionCanceledException{}
	}
	id := stringAttr(in.TransactItems[1].Put.Item, "archiveId")
	message := stringAttr(in.TransactItems[2].Put.Item, "messageId")
	d.keys[key] = in.TransactItems[0].Put.Item
	d.runs[id] = in.TransactItems[1].Put.Item
	d.outbox[message] = in.TransactItems[2].Put.Item
	return &dynamodb.TransactWriteItemsOutput{}, nil
}
func (d *recordingDynamo) GetItem(_ context.Context, in *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if *in.TableName == "coordinator_submission_keys" {
		return &dynamodb.GetItemOutput{Item: d.keys[stringAttr(in.Key, "idempotencyKey")]}, nil
	}
	return &dynamodb.GetItemOutput{Item: d.runs[stringAttr(in.Key, "archiveId")]}, nil
}

func request() archive.Submission {
	depth, pages := 2, 5
	return archive.Submission{SeedURL: "https://example.com/", MaxDepth: &depth, MaxPages: &pages}
}
func response(id string) archive.AcceptedResponse {
	return archive.AcceptedResponse{ArchiveID: id, Status: archive.Accepted, StatusURL: "/archives/" + id}
}

func TestAdmission_AtomicallyRecordsRunAndStartCommand(t *testing.T) {
	db := newDynamo()
	store := New(db, "")
	accepted, err := store.Admit(context.Background(), "unique-key", "digest", response("run-1"), request(), time.Now())
	require.NoError(t, err)

	assert.Equal(t, "run-1", accepted.ArchiveID)
	assert.Len(t, db.keys, 1)
	assert.Len(t, db.runs, 1)
	assert.Len(t, db.outbox, 1)
	assert.Equal(t, "PENDING", stringAttr(db.outbox["run-1:start:1"], "state"))
}

func TestAdmission_ConcurrentRetriesProduceOneRun(t *testing.T) {
	db := newDynamo()
	store := New(db, "")
	var wg sync.WaitGroup
	results := make(chan archive.AcceptedResponse, 100)
	failures := make(chan error, 100)
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			accepted, err := store.Admit(context.Background(), "same-key", "same-digest", response("run-1"), request(), time.Now())
			results <- accepted
			failures <- err
		}()
	}
	wg.Wait()
	close(results)
	close(failures)
	for err := range failures {
		require.NoError(t, err)
	}
	for accepted := range results {
		assert.Equal(t, "run-1", accepted.ArchiveID)
	}
	assert.Len(t, db.keys, 1)
	assert.Len(t, db.runs, 1)
	assert.Len(t, db.outbox, 1)
}

func TestAdmission_ChangingRequestUnderExistingKeyIsRejected(t *testing.T) {
	db := newDynamo()
	store := New(db, "")
	_, err := store.Admit(context.Background(), "same-key", "first", response("run-1"), request(), time.Now())
	require.NoError(t, err)
	_, err = store.Admit(context.Background(), "same-key", "second", response("run-2"), request(), time.Now())

	assert.True(t, errors.Is(err, application.ErrConflict))
	assert.Len(t, db.runs, 1)
	assert.Len(t, db.outbox, 1)
}
