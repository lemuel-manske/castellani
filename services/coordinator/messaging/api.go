// Package messaging defines the Coordinator's asynchronous messaging contracts.
package messaging

import (
	"context"
	"time"
)

type Message struct {
	ID      string
	Type    string
	Payload []byte
	Lease   string
}

type Outbox interface {
	Claim(context.Context, time.Duration) (Message, bool, error)

	Confirm(context.Context, Message) error
}

type Publisher interface {
	Publish(context.Context, Message) error
}
