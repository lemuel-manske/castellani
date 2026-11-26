// Package contracts contains Coordinator message wire types.
package contracts

// Keep these definitions in sync with the repository-root
// contracts/messages/start-crawl.v1.schema.json, which is the source of truth.
const (
	StartCrawlType  = "StartCrawl"

	EnvelopeVersion = 1
)

type StartCrawlEnvelope struct {
	MessageID     string            `json:"messageId"`
	CorrelationID string            `json:"correlationId"`
	Type          string            `json:"type"`
	Version       int               `json:"version"`
	OccurredAt    string            `json:"occurredAt"`
	Payload       StartCrawlPayload `json:"payload"`
}

type StartCrawlPayload struct {
	ArchiveID      string   `json:"archiveId"`
	SeedURL        string   `json:"seedUrl"`
	MaxDepth       int      `json:"maxDepth"`
	MaxPages       int      `json:"maxPages"`
	CollectionID   string   `json:"collectionId,omitempty"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}
