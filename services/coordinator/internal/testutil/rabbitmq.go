package testutil

import (
	"encoding/json"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/require"
)

func Subscribe(
	t *testing.T,
	connection *amqp.Connection,
	exchange, routingKey string,
) <-chan amqp.Delivery {
	t.Helper()

	channel, err := connection.Channel()
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, channel.Close())
	})

	queue, err := channel.QueueDeclare(
		"",
		false,
		true,
		true,
		false,
		nil,
	)
	require.NoError(t, err)

	err = channel.QueueBind(
		queue.Name,
		routingKey,
		exchange,
		false,
		nil,
	)
	require.NoError(t, err)

	deliveries, err := channel.Consume(
		queue.Name,
		"",
		true,
		true,
		false,
		false,
		nil,
	)
	require.NoError(t, err)

	return deliveries
}

func RequireNoMessage(t *testing.T, deliveries <-chan amqp.Delivery) {
	t.Helper()

	require.Never(
		t,
		func() bool {
			select {
			case <-deliveries:
				return true
			default:
				return false
			}
		},
		time.Second,
		10*time.Millisecond,
	)
}

func Publish(
	t *testing.T,
	connection *amqp.Connection,
	exchange, routingKey string,
	message any,
) {
	t.Helper()

	body, err := json.Marshal(message)
	require.NoError(t, err)

	channel, err := connection.Channel()
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, channel.Close())
	})

	err = channel.PublishWithContext(
		t.Context(),
		exchange,
		routingKey,
		true,
		false,
		amqp.Publishing{
			DeliveryMode: amqp.Persistent,
			ContentType:  "application/json",
			Body:         body,
		},
	)
	require.NoError(t, err)
}

func Receive(t *testing.T, deliveries <-chan amqp.Delivery) amqp.Delivery {
	t.Helper()

	var delivery amqp.Delivery

	require.Eventually(
		t,
		func() bool {
			select {
			case received, ok := <-deliveries:
				if !ok {
					return false
				}

				delivery = received

				return true
			default:
				return false
			}
		},
		5*time.Second,
		10*time.Millisecond,
	)

	return delivery
}
