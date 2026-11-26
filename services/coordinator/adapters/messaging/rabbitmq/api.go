// Package rabbitmq implements the Coordinator's message transport.
package rabbitmq

import "github.com/lemuel-manske/castellani/services/coordinator/domain"

const (
	HeaderAttempt = "x-coordinator-attempt"
)

var EventTypes = []string{
	domain.EventCrawlCompleted,
	domain.EventArchivePrepared,
	domain.EventArchivePublished,
	domain.EventArchiveCompensated,
	domain.EventSearchCompensated,
	domain.EventSearchIndexingCompleted,
	domain.EventSearchReady,
}

type RabbitConsumer struct {
	url       string
	publisher *RabbitPublisher
}

type RabbitPublisher struct {
	url string
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

func NewRabbitConsumer(url string, publisher *RabbitPublisher) *RabbitConsumer {
	return &RabbitConsumer{
		url:       url,
		publisher: publisher,
	}
}

func NewRabbitPublisher(url string) *RabbitPublisher {
	return &RabbitPublisher{
		url: url,
	}
}
