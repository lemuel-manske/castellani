// Package dispatcher delivers messages from the Coordinator's outbox.
package dispatcher

import (
	"github.com/lemuel-manske/castellani/services/coordinator/application"
)

type Dispatcher struct {
	outbox    application.Outbox
	publisher application.Publisher
}

func NewDispatcher(outbox application.Outbox, publisher application.Publisher) *Dispatcher {
	return &Dispatcher{
		outbox:    outbox,
		publisher: publisher,
	}
}
