package rabbitmq

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"

	"github.com/lemuel-manske/castellani/services/coordinator/domain"
	amqp "github.com/rabbitmq/amqp091-go"
)

const (
	maxDeliveryAttempts    = 5
	prefetchCount          = 8
	retryDelayMilliseconds = 5000
)

func (c *RabbitConsumer) Consume(
	ctx context.Context,
	handle func(context.Context, domain.Event) error,
) error {
	conn, err := amqp.Dial(c.url)

	if err != nil {
		return fmt.Errorf("connect to RabbitMQ: %w", err)
	}
	defer conn.Close()

	channel, err := conn.Channel()

	if err != nil {
		return fmt.Errorf("open consumer channel: %w", err)
	}
	defer channel.Close()

	if err = c.declareTopology(channel); err != nil {
		return err
	}

	if err = channel.Qos(
		prefetchCount,
		0,
		false,
	); err != nil {
		return fmt.Errorf("set consumer prefetch: %w", err)
	}

	deliveries, err := channel.Consume(
		CoordinatorQueue,
		"",
		false,
		false,
		false,
		false,
		nil,
	)

	if err != nil {
		return fmt.Errorf("consume coordinator queue: %w", err)
	}

	for {
		select {
		case <-ctx.Done():
			return nil
		case delivery, ok := <-deliveries:
			if !ok {
				return errors.New("coordinator consumer delivery stream closed")
			}

			event, decodeErr := decodeEvent(delivery.Body)

			if decodeErr != nil {
				if err := delivery.Nack(false, false); err != nil {
					return err
				}

				continue
			}

			err := handle(ctx, event)

			if err == nil {
				if ackErr := delivery.Ack(false); ackErr != nil {
					return ackErr
				}

				continue
			}

			if errors.Is(err, domain.ErrInvalidEvent) {
				if nackErr := delivery.Nack(false, false); nackErr != nil {
					return nackErr
				}

				continue
			}

			attempts := messageAttempts(delivery.Headers)

			if attempts >= maxDeliveryAttempts {
				if nackErr := delivery.Nack(false, false); nackErr != nil {
					return nackErr
				}

				continue
			}

			if retryErr := c.publisher.PublishRetry(
				ctx,
				event,
				delivery.Body,
				attempts+1,
			); retryErr != nil {
				// Preserve the original delivery when retry publication cannot
				// be confirmed. This may redeliver but cannot lose the event.
				return fmt.Errorf("schedule retry: %w", retryErr)
			}

			if ackErr := delivery.Ack(false); ackErr != nil {
				return ackErr
			}
		}
	}
}

func (c *RabbitConsumer) declareTopology(channel *amqp.Channel) error {
	for _, exchange := range []string{c.exchange, DeadExchange} {
		if err := channel.ExchangeDeclare(
			exchange,
			"topic",
			true,
			false,
			false,
			false,
			nil,
		); err != nil {
			return fmt.Errorf(
				"declare exchange %s: %w",
				exchange,
				err,
			)
		}
	}

	_, err := channel.QueueDeclare(
		DeadQueue,
		true,
		false,
		false,
		false,
		nil,
	)

	if err != nil {
		return fmt.Errorf("declare dead letter queue: %w", err)
	}

	if err := channel.QueueBind(
		DeadQueue,
		"#",
		DeadExchange,
		false,
		nil,
	); err != nil {
		return fmt.Errorf("bind dead letter queue: %w", err)
	}

	_, err = channel.QueueDeclare(
		RetryQueue,
		true,
		false,
		false,
		false,
		amqp.Table{
			"x-message-ttl":             int32(retryDelayMilliseconds),
			"x-dead-letter-exchange":    "",
			"x-dead-letter-routing-key": CoordinatorQueue,
		},
	)

	if err != nil {
		return fmt.Errorf("declare retry queue: %w", err)
	}

	_, err = channel.QueueDeclare(
		CoordinatorQueue,
		true,
		false,
		false,
		false,
		amqp.Table{
			"x-dead-letter-exchange": DeadExchange,
		},
	)

	if err != nil {
		return fmt.Errorf("declare coordinator queue: %w", err)
	}

	for _, eventType := range EventTypes {
		if err := channel.QueueBind(
			CoordinatorQueue,
			eventType,
			c.exchange,
			false,
			nil,
		); err != nil {
			return fmt.Errorf(
				"bind %s: %w",
				eventType,
				err,
			)
		}
	}

	return nil
}

func decodeEvent(data []byte) (domain.Event, error) {
	var wire InboundEnvelope

	if err := json.Unmarshal(data, &wire); err != nil {
		return domain.Event{}, fmt.Errorf("decode event: %w", err)
	}

	recognized := slices.Contains(EventTypes, wire.Type)

	if !recognized || wire.Version != 1 || wire.MessageID == "" || wire.Payload.ArchiveID == "" ||
		wire.CorrelationID != wire.Payload.ArchiveID {
		return domain.Event{}, domain.ErrInvalidEvent
	}

	return domain.Event{
		MessageID:       wire.MessageID,
		ArchiveID:       wire.Payload.ArchiveID,
		Type:            wire.Type,
		ManifestDigest:  wire.Payload.ManifestDigest,
		PackageDigest:   wire.Payload.PackageDigest,
		DecisionVersion: wire.Payload.DecisionVersion,
		SeedSucceeded:   wire.Payload.SeedSucceeded,
		Captured:        wire.Payload.Captured,
		Failed:          wire.Payload.Failed,
		Indexed:         wire.Payload.Indexed,
		Expected:        wire.Payload.Expected,
	}, nil
}

func messageAttempts(headers amqp.Table) int {
	switch value := headers[HeaderAttempt].(type) {
	case int32:
		return int(value)
	case int64:
		return int(value)
	case int:
		return value
	default:
		return 0
	}
}
