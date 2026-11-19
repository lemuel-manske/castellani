// Package dynamodb implements Coordinator persistence using DynamoDB.
package dynamodb

import (
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
)

const archiveTimestampLayout = "2006-01-02T15:04:05.000000000Z07:00"

const (
	OutboxClaimed   = "CLAIMED"
	OutboxPending   = "PENDING"
	OutboxPublished = "PUBLISHED"

	StartCrawlType = "StartCrawl"
)

type Tables struct {
	Archives    string
	Submissions string
	Outbox      string
	Inbox       string
}

type DynamoArchiveRepository struct {
	client *dynamodb.Client
	tables Tables
}

type AdmissionKey struct {
	archiveID   string
	fingerprint string
}

type StartCrawlEnvelope struct {
	MessageID     string            `json:"messageId"`
	CorrelationID string            `json:"correlationId"`
	Type          string            `json:"type"`
	Version       int               `json:"version"`
	OccurredAt    string            `json:"occurredAt"`
	Payload       StartCrawlPayload `json:"payload"`
}

type StartCrawlPayload struct {
	ArchiveID      string   `json:"archiveId"`
	SeedURL        string   `json:"seedUrl"`
	MaxDepth       int      `json:"maxDepth"`
	MaxPages       int      `json:"maxPages"`
	CollectionID   string   `json:"collectionId,omitempty"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}

func NewDynamoArchiveRepository(client *dynamodb.Client, tables Tables) *DynamoArchiveRepository {
	return &DynamoArchiveRepository{
		client: client,
		tables: tables,
	}
}
