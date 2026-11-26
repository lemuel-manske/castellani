package application

import (
	"context"
	"fmt"
	"time"
)

const outboxLeaseDuration = 30 * time.Second

type OutboxDispatcher struct {
	outbox    Outbox
	publisher Publisher
}

func NewOutboxDispatcher(outbox Outbox, publisher Publisher) *OutboxDispatcher {
	return &OutboxDispatcher{
		outbox:    outbox,
		publisher: publisher,
	}
}

func (d *OutboxDispatcher) Dispatch(ctx context.Context) (bool, error) {
	message, found, err := d.outbox.Claim(ctx, outboxLeaseDuration)

	if err != nil || !found {
		return found, err
	}

	if err := d.publisher.Publish(ctx, message); err != nil {
		return true, fmt.Errorf(
			"publish %s: %w",
			message.ID,
			err,
		)
	}

	if err := d.outbox.Confirm(ctx, message); err != nil {
		return true, fmt.Errorf(
			"confirm delivery %s: %w",
			message.ID,
			err,
		)
	}

	return true, nil
}
