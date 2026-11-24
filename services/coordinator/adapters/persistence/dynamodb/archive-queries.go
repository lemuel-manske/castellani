package dynamodb

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/castellani/services/coordinator/domain"
)

const idempotencyRetention = 48 * time.Hour

type admissionInput struct {
	Key         string
	Fingerprint string
	ArchiveID   string
	MessageID   string
	Envelope    []byte
	Now         time.Time
	Submission  domain.Submission
}

type eventCommitInput struct {
	Before  domain.Archive
	After   domain.Archive
	Event   domain.Event
	Effects []domain.Effect
	Now     time.Time
}

type recoveryCommitInput struct {
	Archive   domain.Archive
	Effect    domain.Effect
	MessageID string
	Envelope  []byte
	Now       time.Time
}

func findAdmissionKey(
	ctx context.Context,
	client *dynamodb.Client,
	key string,
) (AdmissionKey, bool, error) {
	response, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(SubmissionsTable),
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

func getArchive(
	ctx context.Context,
	client *dynamodb.Client,
	id string,
) (domain.Archive, bool, error) {
	response, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(ArchivesTable),
		ConsistentRead: aws.Bool(true),
		Key: map[string]types.AttributeValue{
			"archiveId": &types.AttributeValueMemberS{
				Value: id,
			},
		},
	})

	if err != nil {
		return domain.Archive{}, false, fmt.Errorf("read archive: %w", err)
	}

	if len(response.Item) == 0 {
		return domain.Archive{}, false, nil
	}

	return archiveFromItem(id, response.Item), true, nil
}

func commitAdmission(
	ctx context.Context,
	client *dynamodb.Client,
	input admissionInput,
) error {
	transaction := []types.TransactWriteItem{
		{
			Put: &types.Put{
				TableName:           aws.String(SubmissionsTable),
				ConditionExpression: aws.String("attribute_not_exists(idempotencyKey)"),
				Item: map[string]types.AttributeValue{
					"idempotencyKey": &types.AttributeValueMemberS{
						Value: input.Key,
					},
					"fingerprint": &types.AttributeValueMemberS{
						Value: input.Fingerprint,
					},
					"archiveId": &types.AttributeValueMemberS{
						Value: input.ArchiveID,
					},
					"createdAt": &types.AttributeValueMemberS{
						Value: input.Now.Format(time.RFC3339Nano),
					},
					"expiresAt": &types.AttributeValueMemberN{
						Value: strconv.FormatInt(input.Now.Add(idempotencyRetention).Unix(), 10),
					},
				},
			},
		},
		{
			Put: &types.Put{
				TableName:           aws.String(ArchivesTable),
				ConditionExpression: aws.String("attribute_not_exists(archiveId)"),
				Item: map[string]types.AttributeValue{
					"archiveId": &types.AttributeValueMemberS{
						Value: input.ArchiveID,
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
						Value: input.Fingerprint,
					},
					"seedUrl": &types.AttributeValueMemberS{
						Value: input.Submission.SeedURL,
					},
					"createdAt": &types.AttributeValueMemberS{
						Value: input.Now.Format(time.RFC3339Nano),
					},
					"updatedAt": &types.AttributeValueMemberS{
						Value: input.Now.Format(archiveTimestampLayout),
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
		outboxPut(
			input.MessageID,
			StartCrawlType,
			input.Envelope,
			input.Now,
		),
	}

	_, err := client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: transaction,
	})

	return err
}

func commitEvent(
	ctx context.Context,
	client *dynamodb.Client,
	input eventCommitInput,
) error {
	updates := map[string]types.AttributeValue{
		"status": &types.AttributeValueMemberS{
			Value: input.After.Status,
		},
		"decision": &types.AttributeValueMemberS{
			Value: input.After.Decision,
		},
		"decisionVersion": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.After.DecisionVersion),
		},
		"crawlTerminal": &types.AttributeValueMemberBOOL{
			Value: input.After.CrawlTerminal,
		},
		"seedSucceeded": &types.AttributeValueMemberBOOL{
			Value: input.After.SeedSucceeded,
		},
		"manifestDigest": &types.AttributeValueMemberS{
			Value: input.After.ManifestDigest,
		},
		"preparedDigest": &types.AttributeValueMemberS{
			Value: input.After.PreparedManifestDigest,
		},
		"packageDigest": &types.AttributeValueMemberS{
			Value: input.After.PackageDigest,
		},
		"captureCompensated": &types.AttributeValueMemberBOOL{
			Value: input.After.CaptureCompensated,
		},
		"searchCompensated": &types.AttributeValueMemberBOOL{
			Value: input.After.SearchCompensated,
		},
		"captured": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.After.Capture.Captured),
		},
		"failed": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.After.Capture.Failed),
		},
		"pending": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.After.Capture.Pending),
		},
		"replayStatus": &types.AttributeValueMemberS{
			Value: input.After.Replay.Status,
		},
		"searchStatus": &types.AttributeValueMemberS{
			Value: input.After.Search.Status,
		},
		"indexed": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.After.Search.Indexed),
		},
		"expected": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.After.Search.Expected),
		},
		"revision": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.Before.Revision + 1),
		},
		"updatedAt": &types.AttributeValueMemberS{
			Value: input.Now.Format(archiveTimestampLayout),
		},
		"recoveryKey": &types.AttributeValueMemberS{
			Value: recoveryKey(input.After),
		},
	}

	// A condition on the monotonically increasing revision prevents
	// concurrent replicas from making different decisions.
	transaction := []types.TransactWriteItem{
		{
			Put: &types.Put{
				TableName:           aws.String(InboxTable),
				ConditionExpression: aws.String("attribute_not_exists(messageId)"),
				Item: map[string]types.AttributeValue{
					"messageId": &types.AttributeValueMemberS{
						Value: input.Event.MessageID,
					},
					"archiveId": &types.AttributeValueMemberS{
						Value: input.Event.ArchiveID,
					},
					"type": &types.AttributeValueMemberS{
						Value: input.Event.Type,
					},
					"processedAt": &types.AttributeValueMemberS{
						Value: input.Now.Format(time.RFC3339Nano),
					},
				},
			},
		},
	}

	for _, effect := range input.Effects {
		messageID, err := generateMessageID()

		if err != nil {
			return err
		}

		envelope, err := encodeEffect(
			messageID,
			effect,
			input.Now,
		)

		if err != nil {
			return err
		}

		transaction = append(transaction, outboxPut(
			messageID,
			effect.Type,
			envelope,
			input.Now,
		))
	}

	// Build an update using attribute aliases: several state fields are
	// reserved in DynamoDB's expression language.
	names := map[string]string{
		"#revision": "revision",
	}
	values := map[string]types.AttributeValue{
		":expected": &types.AttributeValueMemberN{
			Value: strconv.Itoa(input.Before.Revision),
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
			TableName: aws.String(ArchivesTable),
			Key: map[string]types.AttributeValue{
				"archiveId": &types.AttributeValueMemberS{
					Value: input.Before.ID,
				},
			},
			ConditionExpression:       aws.String("#revision = :expected"),
			UpdateExpression:          aws.String("SET " + strings.Join(assignments, ", ")),
			ExpressionAttributeNames:  names,
			ExpressionAttributeValues: values,
		},
	})

	_, err := client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: transaction,
	})

	return err
}

func inboxHasMessage(
	ctx context.Context,
	client *dynamodb.Client,
	messageID string,
) (bool, error) {
	response, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName:      aws.String(InboxTable),
		ConsistentRead: aws.Bool(true),
		Key: map[string]types.AttributeValue{
			"messageId": &types.AttributeValueMemberS{
				Value: messageID,
			},
		},
	})

	if err != nil {
		return false, fmt.Errorf("resolve event commit: %w", err)
	}

	return len(response.Item) != 0, nil
}

func listStalledArchives(
	ctx context.Context,
	client *dynamodb.Client,
	recovery string,
	before time.Time,
	limit int,
) ([]domain.Archive, error) {
	archives := make(
		[]domain.Archive,
		0,
		limit,
	)

	var cursor map[string]types.AttributeValue

	for len(archives) < limit {
		page, err := client.Query(ctx, &dynamodb.QueryInput{
			TableName:              aws.String(ArchivesTable),
			IndexName:              aws.String("recoveryKey-updatedAt-index"),
			ExclusiveStartKey:      cursor,
			Limit:                  aws.Int32(int32(limit - len(archives))),
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

	return archives, nil
}

func commitRecovery(
	ctx context.Context,
	client *dynamodb.Client,
	input recoveryCommitInput,
) error {
	_, err := client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: []types.TransactWriteItem{
			outboxPut(
				input.MessageID,
				input.Effect.Type,
				input.Envelope,
				input.Now,
			),
			{
				Update: &types.Update{
					TableName: aws.String(ArchivesTable),
					Key: map[string]types.AttributeValue{
						"archiveId": &types.AttributeValueMemberS{
							Value: input.Archive.ID,
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
							Value: strconv.Itoa(input.Archive.Revision),
						},
						":nextRevision": &types.AttributeValueMemberN{
							Value: strconv.Itoa(input.Archive.Revision + 1),
						},
						":updatedAt": &types.AttributeValueMemberS{
							Value: input.Archive.UpdatedAt.Format(archiveTimestampLayout),
						},
						":status": &types.AttributeValueMemberS{
							Value: input.Archive.Status,
						},
						":decision": &types.AttributeValueMemberS{
							Value: input.Archive.Decision,
						},
						":recoveryKey": &types.AttributeValueMemberS{
							Value: recoveryKey(input.Archive),
						},
						":now": &types.AttributeValueMemberS{
							Value: input.Now.Format(archiveTimestampLayout),
						},
					},
				},
			},
		},
	})

	return err
}
