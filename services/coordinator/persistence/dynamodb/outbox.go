package dynamodb

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/castellani/services/coordinator/messaging"
)

const (
	outboxClaimLimit = 50
)

func (r *DynamoRepository) Claim(
	ctx context.Context,
	lease time.Duration,
) (messaging.Message, bool, error) {
	now := time.Now().UTC()
	expired := now.Unix()

	var cursor map[string]types.AttributeValue

	for {
		page, err := r.client.Scan(ctx, &dynamodb.ScanInput{
			ExclusiveStartKey: cursor,
			TableName:         aws.String(r.tables.Outbox),
			Limit:             aws.Int32(outboxClaimLimit),
			FilterExpression:  aws.String("#state = :pending OR (#state = :claimed AND leaseUntil < :now)"),
			ExpressionAttributeNames: map[string]string{
				"#state": "state",
			},
			ExpressionAttributeValues: map[string]types.AttributeValue{
				":pending": &types.AttributeValueMemberS{
					Value: OutboxPending,
				},
				":claimed": &types.AttributeValueMemberS{
					Value: OutboxClaimed,
				},
				":now": &types.AttributeValueMemberN{
					Value: fmt.Sprint(expired),
				},
			},
		})

		if err != nil {
			return messaging.Message{}, false, fmt.Errorf("scan outbox: %w", err)
		}

		for _, item := range page.Items {
			id := stringValue(item["messageId"])

			if id == "" {
				return messaging.Message{}, false, errors.New("outbox item missing messageId")
			}

			token, err := generateID("lease-")

			if err != nil {
				return messaging.Message{}, false, err
			}

			updated, err := r.client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
				TableName: aws.String(r.tables.Outbox),
				Key: map[string]types.AttributeValue{
					"messageId": &types.AttributeValueMemberS{
						Value: id,
					},
				},
				ConditionExpression: aws.String("#state = :pending OR (#state = :claimed AND leaseUntil < :now)"),
				UpdateExpression:    aws.String("SET #state = :claimed, leaseToken = :token, leaseUntil = :until ADD attempts :increment"),
				ExpressionAttributeNames: map[string]string{
					"#state": "state",
				},
				ExpressionAttributeValues: map[string]types.AttributeValue{
					":pending": &types.AttributeValueMemberS{
						Value: OutboxPending,
					},
					":claimed": &types.AttributeValueMemberS{
						Value: OutboxClaimed,
					},
					":now": &types.AttributeValueMemberN{
						Value: fmt.Sprint(expired),
					},
					":until": &types.AttributeValueMemberN{
						Value: fmt.Sprint(now.Add(lease).Unix()),
					},
					":token": &types.AttributeValueMemberS{
						Value: token,
					},
					":increment": &types.AttributeValueMemberN{
						Value: "1",
					},
				},
				ReturnValues: types.ReturnValueAllNew,
			})

			if err != nil {
				var failed *types.ConditionalCheckFailedException

				if errors.As(err, &failed) {
					continue
				}

				return messaging.Message{}, false, fmt.Errorf("claim outbox entry: %w", err)
			}

			return messaging.Message{
				ID:      id,
				Type:    stringValue(updated.Attributes["type"]),
				Payload: []byte(stringValue(updated.Attributes["envelope"])),
				Lease:   token,
			}, true, nil
		}

		if len(page.LastEvaluatedKey) == 0 {
			return messaging.Message{}, false, nil
		}

		cursor = page.LastEvaluatedKey
	}
}

func (r *DynamoRepository) Confirm(ctx context.Context, message messaging.Message) error {
	_, err := r.client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(r.tables.Outbox),
		Key: map[string]types.AttributeValue{
			"messageId": &types.AttributeValueMemberS{
				Value: message.ID,
			},
		},
		ConditionExpression: aws.String("#state = :claimed AND leaseToken = :token"),
		UpdateExpression:    aws.String("SET #state = :published, publishedAt = :now REMOVE leaseToken, leaseUntil"),
		ExpressionAttributeNames: map[string]string{
			"#state": "state",
		},
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":claimed": &types.AttributeValueMemberS{
				Value: OutboxClaimed,
			},
			":token": &types.AttributeValueMemberS{
				Value: message.Lease,
			},
			":published": &types.AttributeValueMemberS{
				Value: OutboxPublished,
			},
			":now": &types.AttributeValueMemberS{
				Value: time.Now().UTC().Format(time.RFC3339Nano),
			},
		},
	})

	if err != nil {
		return fmt.Errorf("confirm outbox record: %w", err)
	}

	return nil
}
