// Package dispatcher delivers messages from the Coordinator's outbox.
package dispatcher

import (
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
