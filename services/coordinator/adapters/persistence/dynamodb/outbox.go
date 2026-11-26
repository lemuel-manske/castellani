package dynamodb

import (
	"context"
	"errors"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/lemuel-manske/castellani/services/coordinator/application"
)

func (r *DynamoOutboxRepository) Claim(
	ctx context.Context,
	lease time.Duration,
) (application.Message, bool, error) {
	now := time.Now().UTC()
	expired := now.Unix()

	var cursor map[string]types.AttributeValue

	for {
		page, err := scanClaimableOutbox(
			ctx,
			r.client,
			cursor,
			expired,
		)

		if err != nil {
			return application.Message{}, false, err
		}

		for _, item := range page.Items {
			id := stringValue(item["messageId"])

			if id == "" {
				return application.Message{}, false, errors.New("outbox item missing messageId")
			}

			token, err := generateLeaseToken()

			if err != nil {
				return application.Message{}, false, err
			}

			message, claimed, err := claimOutboxEntry(
				ctx,
				r.client,
				id,
				token,
				now,
				lease,
				expired,
			)

			if err != nil {
				return application.Message{}, false, err
			}

			if claimed {
				return message, true, nil
			}
		}

		if len(page.LastEvaluatedKey) == 0 {
			return application.Message{}, false, nil
		}

		cursor = page.LastEvaluatedKey
	}
}

func (r *DynamoOutboxRepository) Confirm(ctx context.Context, message application.Message) error {
	return confirmOutboxEntry(
		ctx,
		r.client,
		message,
	)
}
