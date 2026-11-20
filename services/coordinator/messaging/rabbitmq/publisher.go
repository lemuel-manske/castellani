package rabbitmq

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/lemuel-manske/castellani/services/coordinator/domain"
	"github.com/lemuel-manske/castellani/services/coordinator/messaging"
	amqp "github.com/rabbitmq/amqp091-go"
)

const publishTimeout = 15 * time.Second

func (p *RabbitPublisher) Publish(ctx context.Context, message messaging.Message) error {
	publishing := amqp.Publishing{
		DeliveryMode: amqp.Persistent,
		ContentType:  "application/json",
		MessageId:    message.ID,
		Body:         message.Payload,
	}

	return p.publish(
		ctx,
		p.exchange,
		message.Type,
		publishing,
	)
}

func (p *RabbitPublisher) PublishRetry(
	ctx context.Context,
	event domain.Event,
	payload []byte,
	attempt int,
) error {
	publishing := amqp.Publishing{
		DeliveryMode: amqp.Persistent,
		ContentType:  "application/json",
		MessageId:    event.MessageID,
		Body:         payload,
		Headers: amqp.Table{
			HeaderAttempt: int32(attempt),
		},
	}

	return p.publish(
		ctx,
		RetryExchange,
		event.Type,
		publishing,
	)
}

func (p *RabbitPublisher) publish(
	ctx context.Context,
	exchange, routingKey string,
	message amqp.Publishing,
) error {
	connection, err := amqp.Dial(p.url)

	if err != nil {
		return fmt.Errorf("connect RabbitMQ: %w", err)
	}
	defer connection.Close()

	channel, err := connection.Channel()

	if err != nil {
		return fmt.Errorf("open RabbitMQ channel: %w", err)
	}
	defer channel.Close()

	if err = channel.Confirm(false); err != nil {
		return fmt.Errorf("enable publisher confirms: %w", err)
	}

	confirms := channel.NotifyPublish(make(chan amqp.Confirmation, 1))
	returns := channel.NotifyReturn(make(chan amqp.Return, 1))

	deadline, cancel := context.WithTimeout(ctx, publishTimeout)
	defer cancel()

	err = channel.PublishWithContext(
		deadline,
		exchange,
		routingKey,
		true,
		false,
		message,
	)

	if err != nil {
		return fmt.Errorf("publish message: %w", err)
	}

	select {
	case returned := <-returns:
		return fmt.Errorf(
			"unroutable message %s: %s",
			message.MessageId,
			returned.ReplyText,
		)
	case confirm, ok := <-confirms:
		if !ok || !confirm.Ack {
			return errors.New("publisher did not confirm delivery")
		}

		select {
		case returned := <-returns:
			return fmt.Errorf(
				"unroutable message %s: %s",
				message.MessageId,
				returned.ReplyText,
			)
		default:
		}

		return nil
	case <-deadline.Done():
		return deadline.Err()
	}
}
