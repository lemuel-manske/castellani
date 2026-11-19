package dynamodb

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/unnamed/services/coordinator/persistence"
	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
)

const (
	idempotencyRetention = 48 * time.Hour

	admissionAttempts   = 5
	admissionRetryDelay = 30 * time.Millisecond

	messageVersion = 1
)

func (r *DynamoArchiveRepository) Admit(ctx context.Context, admission persistence.Admission) (persistence.AcceptedArchive, error) {
	archiveID, err := generateID("run-")

	if err != nil {
		return persistence.AcceptedArchive{}, err
	}

	messageID, err := generateID("msg-")

	if err != nil {
		return persistence.AcceptedArchive{}, err
	}

	now := time.Now().UTC()

	command := StartCrawlEnvelope{
		MessageID:     messageID,
		CorrelationID: archiveID,
		Type:          StartCrawlType,
		Version:       messageVersion,
		OccurredAt:    now.Format(time.RFC3339Nano),
		Payload: StartCrawlPayload{
			ArchiveID:      archiveID,
			SeedURL:        admission.Submission.SeedURL,
			MaxDepth:       *admission.Submission.MaxDepth,
			MaxPages:       *admission.Submission.MaxPages,
			CollectionID:   admission.Submission.CollectionID,
			AllowedOrigins: admission.Submission.AllowedOrigins,
			AuthGeneration: admission.Submission.AuthGeneration,
		},
	}

	envelope, err := json.Marshal(command)

	if err != nil {
		return persistence.AcceptedArchive{}, fmt.Errorf("encode StartCrawl: %w", err)
	}

	transaction := &dynamodb.TransactWriteItemsInput{
		TransactItems: []types.TransactWriteItem{
			{
				Put: &types.Put{
					TableName:           aws.String(r.tables.Submissions),
					ConditionExpression: aws.String("attribute_not_exists(idempotencyKey)"),
					Item: map[string]types.AttributeValue{
						"idempotencyKey": &types.AttributeValueMemberS{
							Value: admission.Key,
						},
						"fingerprint": &types.AttributeValueMemberS{
							Value: admission.Fingerprint,
						},
						"archiveId": &types.AttributeValueMemberS{
							Value: archiveID,
						},
						"createdAt": &types.AttributeValueMemberS{
							Value: now.Format(time.RFC3339Nano),
						},
						"expiresAt": &types.AttributeValueMemberN{
							Value: strconv.FormatInt(now.Add(idempotencyRetention).Unix(), 10),
						},
					},
				},
			},
			{
				Put: &types.Put{
					TableName:           aws.String(r.tables.Archives),
					ConditionExpression: aws.String("attribute_not_exists(archiveId)"),
					Item: map[string]types.AttributeValue{
						"archiveId": &types.AttributeValueMemberS{
							Value: archiveID,
						},
						"status": &types.AttributeValueMemberS{
							Value: domain.StatusAccepted,
						},
						"decision": &types.AttributeValueMemberS{
							Value: domain.DecisionNone,
						},
						"recoveryKey": &types.AttributeValueMemberS{
							Value: "NONE",
						},
						"revision": &types.AttributeValueMemberN{
							Value: "0",
						},
						"fingerprint": &types.AttributeValueMemberS{
							Value: admission.Fingerprint,
						},
						"seedUrl": &types.AttributeValueMemberS{
							Value: admission.Submission.SeedURL,
						},
						"createdAt": &types.AttributeValueMemberS{
							Value: now.Format(time.RFC3339Nano),
						},
						"updatedAt": &types.AttributeValueMemberS{
							Value: now.Format(archiveTimestampLayout),
						},
						"captured": &types.AttributeValueMemberN{
							Value: "0",
						},
						"failed": &types.AttributeValueMemberN{
							Value: "0",
						},
						"pending": &types.AttributeValueMemberN{
							Value: "0",
						},
						"replayStatus": &types.AttributeValueMemberS{
							Value: domain.ReplayNotReady,
						},
						"searchStatus": &types.AttributeValueMemberS{
							Value: domain.SearchPending,
						},
						"indexed": &types.AttributeValueMemberN{
							Value: "0",
						},
						"expected": &types.AttributeValueMemberN{
							Value: "0",
						},
					},
				},
			},
			{
				Put: &types.Put{
					TableName:           aws.String(r.tables.Outbox),
					ConditionExpression: aws.String("attribute_not_exists(messageId)"),
					Item: map[string]types.AttributeValue{
						"messageId": &types.AttributeValueMemberS{
							Value: messageID,
						},
						"type": &types.AttributeValueMemberS{
							Value: StartCrawlType,
						},
						"state": &types.AttributeValueMemberS{
							Value: OutboxPending,
						},
						"envelope": &types.AttributeValueMemberS{
							Value: string(envelope),
						},
						"createdAt": &types.AttributeValueMemberS{
							Value: now.Format(time.RFC3339Nano),
						},
						"attempts": &types.AttributeValueMemberN{
							Value: "0",
						},
					},
				},
			},
		},
	}

	for attempt := range admissionAttempts {
		existing, found, err := r.findKey(ctx, admission.Key)

		if err != nil {
			return persistence.AcceptedArchive{}, err
		}

		if found {
			if existing.fingerprint != admission.Fingerprint {
				return persistence.AcceptedArchive{}, persistence.ErrIdempotencyConflict
			}

			return persistence.AcceptedArchive{
				ArchiveID: existing.archiveID,
			}, nil
		}

		_, err = r.client.TransactWriteItems(ctx, transaction)

		if err == nil {
			return persistence.AcceptedArchive{
				ArchiveID: archiveID,
			}, nil
		}

		var canceled *types.TransactionCanceledException

		if !errors.As(err, &canceled) {
			// The commit outcome can be uncertain after a transport error;
			// resolve the key before returning a retryable failure.
			existing, found, lookupErr := r.findKey(ctx, admission.Key)

			if lookupErr == nil && found {
				if existing.fingerprint != admission.Fingerprint {
					return persistence.AcceptedArchive{}, persistence.ErrIdempotencyConflict
				}

				return persistence.AcceptedArchive{
					ArchiveID: existing.archiveID,
				}, nil
			}

			return persistence.AcceptedArchive{}, fmt.Errorf("admit archive: %w", err)
		}

		delay := time.Duration(attempt+1) * admissionRetryDelay
		timer := time.NewTimer(delay)

		select {
		case <-ctx.Done():
			timer.Stop()

			return persistence.AcceptedArchive{}, ctx.Err()
		case <-timer.C:
		}
	}

	return persistence.AcceptedArchive{}, errors.New("archive admission contention exceeded retry budget")
}

func (r *DynamoArchiveRepository) Find(ctx context.Context, id string) (domain.Archive, error) {
	response, err := r.client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(r.tables.Archives),
		ConsistentRead: aws.Bool(true),
		Key: map[string]types.AttributeValue{
			"archiveId": &types.AttributeValueMemberS{
				Value: id,
			},
		},
	})

	if err != nil {
		return domain.Archive{}, fmt.Errorf("read archive: %w", err)
	}

	if len(response.Item) == 0 {
		return domain.Archive{}, persistence.ErrArchiveNotFound
	}

	return archiveFromItem(id, response.Item), nil
}

func (r *DynamoArchiveRepository) findKey(ctx context.Context, key string) (AdmissionKey, bool, error) {
	response, err := r.client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(r.tables.Submissions),
		ConsistentRead: aws.Bool(true),
		Key: map[string]types.AttributeValue{
			"idempotencyKey": &types.AttributeValueMemberS{
				Value: key,
			},
		},
	})

	if err != nil {
		return AdmissionKey{}, false, fmt.Errorf("read admission key: %w", err)
	}

	if len(response.Item) == 0 {
		return AdmissionKey{}, false, nil
	}

	archiveID := stringValue(response.Item["archiveId"])
	fingerprint := stringValue(response.Item["fingerprint"])

	if archiveID == "" || fingerprint == "" {
		return AdmissionKey{}, false, errors.New("corrupt admission key record")
	}

	return AdmissionKey{
		archiveID:   archiveID,
		fingerprint: fingerprint,
	}, true, nil
}

func generateID(prefix string) (string, error) {
	var data [16]byte

	if _, err := rand.Read(data[:]); err != nil {
		return "", fmt.Errorf("generate identifier: %w", err)
	}

	return prefix + hex.EncodeToString(data[:]), nil
}

func stringValue(value types.AttributeValue) string {
	attribute, ok := value.(*types.AttributeValueMemberS)

	if !ok {
		return ""
	}

	return attribute.Value
}

func numberValue(value types.AttributeValue) int {
	attribute, ok := value.(*types.AttributeValueMemberN)

	if !ok {
		return 0
	}

	number, _ := strconv.Atoi(attribute.Value)

	return number
}

func boolValue(value types.AttributeValue) bool {
	attribute, ok := value.(*types.AttributeValueMemberBOOL)

	if !ok {
		return false
	}

	return attribute.Value
}

func archiveFromItem(id string, item map[string]types.AttributeValue) domain.Archive {
	updatedAt, _ := time.Parse(archiveTimestampLayout, stringValue(item["updatedAt"]))
	decision := stringValue(item["decision"])

	if decision == "" {
		decision = domain.DecisionNone
	}

	return domain.Archive{
		ID:                     id,
		Status:                 stringValue(item["status"]),
		Revision:               numberValue(item["revision"]),
		UpdatedAt:              updatedAt,
		Decision:               decision,
		DecisionVersion:        numberValue(item["decisionVersion"]),
		CrawlTerminal:          boolValue(item["crawlTerminal"]),
		SeedSucceeded:          boolValue(item["seedSucceeded"]),
		ManifestDigest:         stringValue(item["manifestDigest"]),
		PreparedManifestDigest: stringValue(item["preparedDigest"]),
		PackageDigest:          stringValue(item["packageDigest"]),
		CaptureCompensated:     boolValue(item["captureCompensated"]),
		SearchCompensated:      boolValue(item["searchCompensated"]),
		Capture: domain.CaptureProgress{
			Captured: numberValue(item["captured"]),
			Failed:   numberValue(item["failed"]),
			Pending:  numberValue(item["pending"]),
		},
		Replay: domain.ReplayProgress{
			Status: stringValue(item["replayStatus"]),
		},
		Search: domain.SearchProgress{
			Status:   stringValue(item["searchStatus"]),
			Indexed:  numberValue(item["indexed"]),
			Expected: numberValue(item["expected"]),
		},
	}
}
