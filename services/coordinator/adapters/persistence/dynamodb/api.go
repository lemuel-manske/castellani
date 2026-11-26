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
)

type AdmissionKey struct {
	archiveID   string
	fingerprint string
}

type DynamoArchiveRepository struct {
	client *dynamodb.Client
}

type DynamoOutboxRepository struct {
	client *dynamodb.Client
}

func NewDynamoArchiveRepository(client *dynamodb.Client) *DynamoArchiveRepository {
	return &DynamoArchiveRepository{
		client: client,
	}
}

func NewDynamoOutboxRepository(client *dynamodb.Client) *DynamoOutboxRepository {
	return &DynamoOutboxRepository{
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
