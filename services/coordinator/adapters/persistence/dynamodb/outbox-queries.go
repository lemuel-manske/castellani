package dynamodb

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/castellani/services/coordinator/application"
)

const outboxClaimLimit = 50

type outboxPage struct {
	Items            []map[string]types.AttributeValue
	LastEvaluatedKey map[string]types.AttributeValue
}

func scanClaimableOutbox(
	ctx context.Context,
	client *dynamodb.Client,
	cursor map[string]types.AttributeValue,
	expired int64,
) (outboxPage, error) {
	page, err := client.Scan(ctx, &dynamodb.ScanInput{
		ExclusiveStartKey: cursor,
		TableName:         aws.String(OutboxTable),
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
		return outboxPage{}, fmt.Errorf("scan outbox: %w", err)
	}

	return outboxPage{
		Items:            page.Items,
		LastEvaluatedKey: page.LastEvaluatedKey,
	}, nil
}

func claimOutboxEntry(
	ctx context.Context,
	client *dynamodb.Client,
	id string,
	token string,
	now time.Time,
	lease time.Duration,
	expired int64,
) (application.Message, bool, error) {
	updated, err := client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(OutboxTable),
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
			return application.Message{}, false, nil
		}

		return application.Message{}, false, fmt.Errorf("claim outbox entry: %w", err)
	}

	return application.Message{
		ID:      id,
		Type:    stringValue(updated.Attributes["type"]),
		Payload: []byte(stringValue(updated.Attributes["envelope"])),
		Lease:   token,
	}, true, nil
}

func confirmOutboxEntry(
	ctx context.Context,
	client *dynamodb.Client,
	message application.Message,
) error {
	_, err := client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(OutboxTable),
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
