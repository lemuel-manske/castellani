package dynamodb

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
	"github.com/lemuel-manske/unnamed/services/coordinator/persistence"
)

func (r *DynamoRepository) CommitEvent(
	ctx context.Context,
	before domain.Archive,
	after domain.Archive,
	event domain.Event,
	effects []domain.Effect,
) error {
	now := time.Now().UTC()

	updates := map[string]types.AttributeValue{
		"status": &types.AttributeValueMemberS{
			Value: after.Status,
		},
		"decision": &types.AttributeValueMemberS{
			Value: after.Decision,
		},
		"decisionVersion": &types.AttributeValueMemberN{
			Value: strconv.Itoa(after.DecisionVersion),
		},
		"crawlTerminal": &types.AttributeValueMemberBOOL{
			Value: after.CrawlTerminal,
		},
		"seedSucceeded": &types.AttributeValueMemberBOOL{
			Value: after.SeedSucceeded,
		},
		"manifestDigest": &types.AttributeValueMemberS{
			Value: after.ManifestDigest,
		},
		"preparedDigest": &types.AttributeValueMemberS{
			Value: after.PreparedManifestDigest,
		},
		"packageDigest": &types.AttributeValueMemberS{
			Value: after.PackageDigest,
		},
		"captureCompensated": &types.AttributeValueMemberBOOL{
			Value: after.CaptureCompensated,
		},
		"searchCompensated": &types.AttributeValueMemberBOOL{
			Value: after.SearchCompensated,
		},
		"captured": &types.AttributeValueMemberN{
			Value: strconv.Itoa(after.Capture.Captured),
		},
		"failed": &types.AttributeValueMemberN{
			Value: strconv.Itoa(after.Capture.Failed),
		},
		"pending": &types.AttributeValueMemberN{
			Value: strconv.Itoa(after.Capture.Pending),
		},
		"replayStatus": &types.AttributeValueMemberS{
			Value: after.Replay.Status,
		},
		"searchStatus": &types.AttributeValueMemberS{
			Value: after.Search.Status,
		},
		"indexed": &types.AttributeValueMemberN{
			Value: strconv.Itoa(after.Search.Indexed),
		},
		"expected": &types.AttributeValueMemberN{
			Value: strconv.Itoa(after.Search.Expected),
		},
		"revision": &types.AttributeValueMemberN{
			Value: strconv.Itoa(before.Revision + 1),
		},
		"updatedAt": &types.AttributeValueMemberS{
			Value: now.Format(archiveTimestampLayout),
		},
		"recoveryKey": &types.AttributeValueMemberS{
			Value: recoveryKey(after),
		},
	}

	// A condition on the monotonically increasing revision prevents
	// concurrent replicas from making different decisions.
	transaction := []types.TransactWriteItem{
		{
			Put: &types.Put{
				TableName:           aws.String(r.tables.Inbox),
				ConditionExpression: aws.String("attribute_not_exists(messageId)"),
				Item: map[string]types.AttributeValue{
					"messageId": &types.AttributeValueMemberS{
						Value: event.MessageID,
					},
					"archiveId": &types.AttributeValueMemberS{
						Value: event.ArchiveID,
					},
					"type": &types.AttributeValueMemberS{
						Value: event.Type,
					},
					"processedAt": &types.AttributeValueMemberS{
						Value: now.Format(time.RFC3339Nano),
					},
				},
			},
		},
	}

	for _, effect := range effects {
		messageID, err := generateID("msg-")

		if err != nil {
			return err
		}

		envelope, err := encodeEffect(
			messageID,
			effect,
			now,
		)

		if err != nil {
			return err
		}

		transaction = append(transaction, outboxPut(
			r.tables.Outbox,
			messageID,
			effect.Type,
			envelope,
			now,
		))
	}

	// Build an update using attribute aliases: several state fields are
	// reserved in DynamoDB's expression language.
	names := map[string]string{
		"#revision": "revision",
	}
	values := map[string]types.AttributeValue{
		":expected": &types.AttributeValueMemberN{
			Value: strconv.Itoa(before.Revision),
		},
	}
	keys := make(
		[]string,
		0,
		len(updates),
	)

	for key := range updates {
		keys = append(keys, key)
	}

	sort.Strings(keys)
	assignments := make(
		[]string,
		0,
		len(keys),
	)

	for i, key := range keys {
		name := fmt.Sprintf("#field%d", i)
		value := fmt.Sprintf(":value%d", i)
		names[name] = key
		values[value] = updates[key]
		assignments = append(assignments, name+" = "+value)
	}

	transaction = append(transaction, types.TransactWriteItem{
		Update: &types.Update{
			TableName: aws.String(r.tables.Archives),
			Key: map[string]types.AttributeValue{
				"archiveId": &types.AttributeValueMemberS{
					Value: before.ID,
				},
			},
			ConditionExpression:       aws.String("#revision = :expected"),
			UpdateExpression:          aws.String("SET " + strings.Join(assignments, ", ")),
			ExpressionAttributeNames:  names,
			ExpressionAttributeValues: values,
		},
	})

	_, err := r.client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: transaction,
	})

	if err == nil {
		return nil
	}

	var canceled *types.TransactionCanceledException

	if !errors.As(err, &canceled) {
		return fmt.Errorf("commit archive event: %w", err)
	}

	processed, lookupErr := r.client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(r.tables.Inbox),
		ConsistentRead: aws.Bool(true),
		Key: map[string]types.AttributeValue{
			"messageId": &types.AttributeValueMemberS{
				Value: event.MessageID,
			},
		},
	})

	if lookupErr != nil {
		return fmt.Errorf("resolve event commit: %w", lookupErr)
	}

	if len(processed.Item) != 0 {
		return persistence.ErrAlreadyProcessed
	}

	return persistence.ErrRevisionConflict
}
func (r *DynamoRepository) ListStalled(
	ctx context.Context,
	before time.Time,
	limit int,
) ([]domain.Archive, error) {
	if limit < 1 {
		return nil, errors.New("stalled archive limit must be positive")
	}

	recoveries := []string{"PUBLISH", "COMPENSATE"}

	archives := make(
		[]domain.Archive,
		0,
		limit,
	)

	for _, recovery := range recoveries {
		var cursor map[string]types.AttributeValue

		for len(archives) < limit {
			remaining := limit - len(archives)
			page, err := r.client.Query(ctx, &dynamodb.QueryInput{
				TableName:              aws.String(r.tables.Archives),
				IndexName:              aws.String("recoveryKey-updatedAt-index"),
				ExclusiveStartKey:      cursor,
				Limit:                  aws.Int32(int32(remaining)),
				KeyConditionExpression: aws.String("#recoveryKey = :recoveryKey AND updatedAt <= :before"),
				ExpressionAttributeNames: map[string]string{
					"#recoveryKey": "recoveryKey",
				},
				ExpressionAttributeValues: map[string]types.AttributeValue{
					":recoveryKey": &types.AttributeValueMemberS{
						Value: recovery,
					},
					":before": &types.AttributeValueMemberS{
						Value: before.UTC().Format(archiveTimestampLayout),
					},
				},
			})

			if err != nil {
				return nil, fmt.Errorf("query stalled archives: %w", err)
			}

			for _, item := range page.Items {
				id := stringValue(item["archiveId"])

				if id != "" {
					archives = append(archives, archiveFromItem(id, item))
				}
			}

			if len(page.LastEvaluatedKey) == 0 {
				break
			}

			cursor = page.LastEvaluatedKey
		}

		if len(archives) == limit {
			break
		}
	}

	return archives, nil
}

func (r *DynamoRepository) ScheduleRecovery(
	ctx context.Context,
	archive domain.Archive,
	effect domain.Effect,
) error {
	now := time.Now().UTC()
	messageID, err := generateID("recovery-")

	if err != nil {
		return err
	}

	envelope, err := encodeEffect(
		messageID,
		effect,
		now,
	)

	if err != nil {
		return err
	}

	_, err = r.client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: []types.TransactWriteItem{
			outboxPut(
				r.tables.Outbox,
				messageID,
				effect.Type,
				envelope,
				now,
			),
			{
				Update: &types.Update{
					TableName: aws.String(r.tables.Archives),
					Key: map[string]types.AttributeValue{
						"archiveId": &types.AttributeValueMemberS{
							Value: archive.ID,
						},
					},
					ConditionExpression: aws.String("#revision = :revision AND updatedAt = :updatedAt AND #status = :status AND #decision = :decision AND #recoveryKey = :recoveryKey"),
					UpdateExpression:    aws.String("SET #revision = :nextRevision, updatedAt = :now"),
					ExpressionAttributeNames: map[string]string{
						"#revision":    "revision",
						"#status":      "status",
						"#decision":    "decision",
						"#recoveryKey": "recoveryKey",
					},
					ExpressionAttributeValues: map[string]types.AttributeValue{
						":revision": &types.AttributeValueMemberN{
							Value: strconv.Itoa(archive.Revision),
						},
						":nextRevision": &types.AttributeValueMemberN{
							Value: strconv.Itoa(archive.Revision + 1),
						},
						":updatedAt": &types.AttributeValueMemberS{
							Value: archive.UpdatedAt.Format(archiveTimestampLayout),
						},
						":status": &types.AttributeValueMemberS{
							Value: archive.Status,
						},
						":decision": &types.AttributeValueMemberS{
							Value: archive.Decision,
						},
						":recoveryKey": &types.AttributeValueMemberS{
							Value: recoveryKey(archive),
						},
						":now": &types.AttributeValueMemberS{
							Value: now.Format(archiveTimestampLayout),
						},
					},
				},
			},
		},
	})

	if err == nil {
		return nil
	}

	var canceled *types.TransactionCanceledException

	if errors.As(err, &canceled) {
		return persistence.ErrRevisionConflict
	}

	return fmt.Errorf("schedule archive recovery: %w", err)
}

func encodeEffect(
	messageID string,
	effect domain.Effect,
	now time.Time,
) ([]byte, error) {
	payload := map[string]any{
		"archiveId":       effect.ArchiveID,
		"decisionVersion": effect.DecisionVersion,
	}

	if effect.Type == domain.CommandPublicationDecided {
		payload["packageDigest"] = effect.PackageDigest
	} else {
		payload["reasonCode"] = effect.ReasonCode
	}

	envelope, err := json.Marshal(map[string]any{
		"messageId":     messageID,
		"correlationId": effect.ArchiveID,
		"type":          effect.Type,
		"version":       messageVersion,
		"occurredAt":    now.Format(time.RFC3339Nano),
		"payload":       payload,
	})

	if err != nil {
		return nil, fmt.Errorf(
			"encode %s: %w",
			effect.Type,
			err,
		)
	}

	return envelope, nil
}

func outboxPut(
	table, messageID, messageType string,
	envelope []byte,
	now time.Time,
) types.TransactWriteItem {
	return types.TransactWriteItem{
		Put: &types.Put{
			TableName:           aws.String(table),
			ConditionExpression: aws.String("attribute_not_exists(messageId)"),
			Item: map[string]types.AttributeValue{
				"messageId": &types.AttributeValueMemberS{
					Value: messageID,
				},
				"type": &types.AttributeValueMemberS{
					Value: messageType,
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
	}
}

func recoveryKey(archive domain.Archive) string {
	if archive.Status == domain.StatusFinalizing && archive.Decision == domain.DecisionPublish {
		return "PUBLISH"
	}

	if archive.Status == domain.StatusCompensating && archive.Decision == domain.DecisionCompensate {
		return "COMPENSATE"
	}

	return "NONE"
}
