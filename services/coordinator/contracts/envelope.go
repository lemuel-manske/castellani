package contracts

const EnvelopeVersion = 1

type Envelope[T any] struct {
	MessageID     string `json:"messageId"`
	CorrelationID string `json:"correlationId"`
	Type          string `json:"type"`
	Version       int    `json:"version"`
	OccurredAt    string `json:"occurredAt"`
	Payload       T      `json:"payload"`
}
