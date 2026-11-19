package application

import (
	"context"
	"fmt"
	"time"

	"github.com/lemuel-manske/unnamed/services/coordinator/messaging"
)

type Dispatcher struct {
	outbox    messaging.Outbox
	publisher messaging.Publisher
}

func NewDispatcher(outbox messaging.Outbox, publisher messaging.Publisher) *Dispatcher {
	return &Dispatcher{
		outbox:    outbox,
		publisher: publisher,
	}
}

func (d *Dispatcher) Dispatch(ctx context.Context) (bool, error) {
	message, found, err := d.outbox.Claim(ctx, 30*time.Second)

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
