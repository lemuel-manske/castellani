package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/unnamed/services/coordinator/application"
	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

const (
	retention        = 24 * time.Hour
	runsTable        = "coordinator_archive_runs"
	submissionsTable = "coordinator_submission_keys"
	outboxTable      = "coordinator_outbox"
	startMessageType = "StartCrawl"
	startDestination = "capture.start-crawl"
	outboxPending    = "PENDING"
	initialDecision  = "NONE"
	messageVersion   = 1
)

type Client interface {
	TransactWriteItems(context.Context, *dynamodb.TransactWriteItemsInput, ...func(*dynamodb.Options)) (*dynamodb.TransactWriteItemsOutput, error)
	GetItem(context.Context, *dynamodb.GetItemInput, ...func(*dynamodb.Options)) (*dynamodb.GetItemOutput, error)
}

type Store struct {
	db     Client
	runs   string
	keys   string
	outbox string
}

func New(db Client, prefix string) Store {
	return Store{
		db:     db,
		runs:   prefix + runsTable,
		keys:   prefix + submissionsTable,
		outbox: prefix + outboxTable,
	}
}

type startCrawl struct {
	ArchiveID      string   `json:"archiveId"`
	SeedURL        string   `json:"seedUrl"`
	MaxDepth       int      `json:"maxDepth"`
	MaxPages       int      `json:"maxPages"`
	CollectionID   string   `json:"collectionId,omitempty"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}

type message struct {
	MessageID     string     `json:"messageId"`
	CorrelationID string     `json:"correlationId"`
	Type          string     `json:"type"`
	Version       int        `json:"version"`
	OccurredAt    time.Time  `json:"occurredAt"`
	Payload       startCrawl `json:"payload"`
}

func (s Store) Admit(ctx context.Context, key, digest string, accepted archive.AcceptedResponse, submission archive.Submission, now time.Time) (archive.AcceptedResponse, error) {
	response, err := json.Marshal(accepted)

	if err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("encode admission: %w", err)
	}

	pending := archive.Status{
		ArchiveID: accepted.ArchiveID,
		Status:    archive.Accepted,
		Replay:    archive.Replay{Status: "NOT_READY"},
		Search:    archive.Search{Status: "PENDING"},
	}
	status, err := json.Marshal(pending)

	if err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("encode initial status: %w", err)
	}

	command := message{
		MessageID:     accepted.ArchiveID + ":start:1",
		CorrelationID: accepted.ArchiveID,
		Type:          startMessageType,
		Version:       messageVersion,
		OccurredAt:    now,
		Payload: startCrawl{
			ArchiveID:      accepted.ArchiveID,
			SeedURL:        submission.SeedURL,
			MaxDepth:       *submission.MaxDepth,
			MaxPages:       *submission.MaxPages,
			CollectionID:   submission.CollectionID,
			AllowedOrigins: submission.AllowedOrigins,
			AuthGeneration: submission.AuthGeneration,
		},
	}
	envelope, err := json.Marshal(command)

	if err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("encode start command: %w", err)
	}

	transaction := []types.TransactWriteItem{
		{
			Put: &types.Put{
				TableName: aws.String(s.keys),
				Item: map[string]types.AttributeValue{
					"idempotencyKey": str(key),
					"digest":         str(digest),
					"archiveId":      str(accepted.ArchiveID),
					"response":       str(string(response)),
					"expiresAt":      num(now.Add(retention).Unix()),
				},
				ConditionExpression: aws.String("attribute_not_exists(idempotencyKey)"),
			},
		},
		{
			Put: &types.Put{
				TableName: aws.String(s.runs),
				Item: map[string]types.AttributeValue{
					"archiveId": str(accepted.ArchiveID),
					"status":    str(string(status)),
					"decision":  str(initialDecision),
					"revision":  num(0),
				},
				ConditionExpression: aws.String("attribute_not_exists(archiveId)"),
			},
		},
		{
			Put: &types.Put{
				TableName: aws.String(s.outbox),
				Item: map[string]types.AttributeValue{
					"messageId":   str(command.MessageID),
					"envelope":    str(string(envelope)),
					"state":       str(outboxPending),
					"destination": str(startDestination),
				},
				ConditionExpression: aws.String("attribute_not_exists(messageId)"),
			},
		},
	}

	_, err = s.db.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: transaction,
	})

	if err == nil {
		return accepted, nil
	}

	var canceled *types.TransactionCanceledException

	if !errors.As(err, &canceled) {
		return archive.AcceptedResponse{}, fmt.Errorf("admit archive: %w", err)
	}

	// Conditional conflicts may be a replay or an unrelated transaction failure.
	return s.resolveAdmission(ctx, key, digest, err)
}

func (s Store) resolveAdmission(ctx context.Context, key, digest string, admissionError error) (archive.AcceptedResponse, error) {
	existing, err := s.db.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(s.keys),
		Key:            map[string]types.AttributeValue{"idempotencyKey": str(key)},
		ConsistentRead: aws.Bool(true),
	})

	if err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("resolve admission: %w", err)
	}

	if len(existing.Item) == 0 {
		return archive.AcceptedResponse{}, fmt.Errorf("admit archive: %w", admissionError)
	}

	if stringAttr(existing.Item, "digest") != digest {
		return archive.AcceptedResponse{}, application.ErrConflict
	}

	var accepted archive.AcceptedResponse
	response := stringAttr(existing.Item, "response")

	if err := json.Unmarshal([]byte(response), &accepted); err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("decode admitted response: %w", err)
	}

	return accepted, nil
}

func (s Store) Status(ctx context.Context, id string) (archive.Status, error) {
	record, err := s.db.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(s.runs),
		Key:            map[string]types.AttributeValue{"archiveId": str(id)},
		ConsistentRead: aws.Bool(true),
	})

	if err != nil {
		return archive.Status{}, fmt.Errorf("read archive: %w", err)
	}

	if len(record.Item) == 0 {
		return archive.Status{}, application.ErrNotFound
	}

	var status archive.Status
	payload := stringAttr(record.Item, "status")

	if err := json.Unmarshal([]byte(payload), &status); err != nil {
		return archive.Status{}, fmt.Errorf("decode archive status: %w", err)
	}

	return status, nil
}

func str(value string) types.AttributeValue {
	return &types.AttributeValueMemberS{Value: value}
}

func num(value int64) types.AttributeValue {
	return &types.AttributeValueMemberN{Value: fmt.Sprint(value)}
}

func stringAttr(item map[string]types.AttributeValue, key string) string {
	value, ok := item[key].(*types.AttributeValueMemberS)

	if !ok {
		return ""
	}

	return value.Value
}
