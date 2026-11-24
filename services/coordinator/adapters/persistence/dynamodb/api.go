// Package dynamodb implements Coordinator persistence using DynamoDB.
package dynamodb

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
)

const (
	OutboxClaimed   = "CLAIMED"
	OutboxPending   = "PENDING"
	OutboxPublished = "PUBLISHED"

	StartCrawlType = "StartCrawl"

	messageVersion = 1
)

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

type DynamoArchiveRepository struct {
	client *dynamodb.Client
}

type DynamoOutbox struct {
	client *dynamodb.Client
}

func NewDynamoArchiveRepository(client *dynamodb.Client) *DynamoArchiveRepository {
	return &DynamoArchiveRepository{
		client: client,
	}
}

func NewDynamoOutbox(client *dynamodb.Client) *DynamoOutbox {
	return &DynamoOutbox{
		client: client,
	}
}

func generateArchiveID() (string, error) {
	return generateID("run-")
}

func generateMessageID() (string, error) {
	return generateID("msg-")
}

func generateRecoveryID() (string, error) {
	return generateID("recovery-")
}

func generateLeaseToken() (string, error) {
	return generateID("lease-")
}

func generateID(prefix string) (string, error) {
	var data [16]byte

	if _, err := rand.Read(data[:]); err != nil {
		return "", fmt.Errorf("generate identifier: %w", err)
	}

	return prefix + hex.EncodeToString(data[:]), nil
}
