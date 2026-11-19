// Package rabbitmq implements the Coordinator's message transport.
package rabbitmq

import "github.com/lemuel-manske/unnamed/services/coordinator/domain"

const (
	DeadExchange  = "castellani.dead"
	RetryExchange = "castellani.retry"

	CoordinatorQueue = "castellani.coordinator"
	DeadQueue        = "castellani.coordinator.dead"
	RetryQueue       = "castellani.coordinator.retry"

	HeaderAttempt = "x-coordinator-attempt"
)

type RabbitConsumer struct {
	url       string
	exchange  string
	publisher *RabbitPublisher
}

type RabbitPublisher struct {
	url      string
	exchange string
}

var EventTypes = []string{
	domain.EventCrawlCompleted,
	domain.EventArchivePrepared,
	domain.EventArchivePublished,
	domain.EventArchiveCompensated,
	domain.EventSearchCompensated,
	domain.EventSearchIndexingCompleted,
	domain.EventSearchReady,
}

type InboundEnvelope struct {
	MessageID     string `json:"messageId"`
	CorrelationID string `json:"correlationId"`
	Type          string `json:"type"`
	Version       int    `json:"version"`
	Payload       struct {
		ArchiveID       string `json:"archiveId"`
		ManifestDigest  string `json:"manifestDigest"`
		PackageDigest   string `json:"packageDigest"`
		DecisionVersion int    `json:"decisionVersion"`
		SeedSucceeded   bool   `json:"seedSucceeded"`
		Captured        int    `json:"capturedCount"`
		Failed          int    `json:"failedCount"`
		Indexed         int    `json:"indexed"`
		Expected        int    `json:"expected"`
	} `json:"payload"`
}

func NewRabbitConsumer(url, exchange string, publisher *RabbitPublisher) *RabbitConsumer {
	return &RabbitConsumer{
		url:       url,
		exchange:  exchange,
		publisher: publisher,
	}
}

func NewRabbitPublisher(url, exchange string) *RabbitPublisher {
	return &RabbitPublisher{
		url:      url,
		exchange: exchange,
	}
}
