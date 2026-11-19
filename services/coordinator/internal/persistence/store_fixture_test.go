package persistence

import (
	"context"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

type recordingDynamo struct {
	mu     sync.Mutex
	keys   map[string]map[string]types.AttributeValue
	runs   map[string]map[string]types.AttributeValue
	outbox map[string]map[string]types.AttributeValue
}

func newDynamo() *recordingDynamo {
	return &recordingDynamo{
		keys:   make(map[string]map[string]types.AttributeValue),
		runs:   make(map[string]map[string]types.AttributeValue),
		outbox: make(map[string]map[string]types.AttributeValue),
	}
}

func (d *recordingDynamo) TransactWriteItems(_ context.Context, input *dynamodb.TransactWriteItemsInput, _ ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()

	key := stringAttr(input.TransactItems[0].Put.Item, "idempotencyKey")

	if _, exists := d.keys[key]; exists {
		return nil, &types.TransactionCanceledException{}
	}

	id := stringAttr(input.TransactItems[1].Put.Item, "archiveId")
	messageID := stringAttr(input.TransactItems[2].Put.Item, "messageId")

	d.keys[key] = input.TransactItems[0].Put.Item
	d.runs[id] = input.TransactItems[1].Put.Item
	d.outbox[messageID] = input.TransactItems[2].Put.Item

	return &dynamodb.TransactWriteItemsOutput{}, nil
}

func (d *recordingDynamo) GetItem(_ context.Context, input *dynamodb.GetItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error) {
	d.mu.Lock()
	defer d.mu.Unlock()

	if *input.TableName == submissionsTable {
		key := stringAttr(input.Key, "idempotencyKey")
		return &dynamodb.GetItemOutput{Item: d.keys[key]}, nil
	}

	id := stringAttr(input.Key, "archiveId")
	return &dynamodb.GetItemOutput{Item: d.runs[id]}, nil
}

func request() archive.Submission {
	depth, pages := 2, 5

	return archive.Submission{
		SeedURL:  "https://example.com/",
		MaxDepth: &depth,
		MaxPages: &pages,
	}
}

func response(id string) archive.AcceptedResponse {
	return archive.AcceptedResponse{
		ArchiveID: id,
		Status:    archive.Accepted,
		StatusURL: "/archives/" + id,
	}
}

func admit(store Store, key, digest, id string) (archive.AcceptedResponse, error) {
	return store.Admit(context.Background(), key, digest, response(id), request(), time.Now())
}
