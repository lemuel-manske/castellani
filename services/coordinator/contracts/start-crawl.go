package contracts

const StartCrawlType = "StartCrawl"

type StartCrawlEnvelope = Envelope[StartCrawlPayload]

type StartCrawlPayload struct {
	ArchiveID      string   `json:"archiveId"`
	SeedURL        string   `json:"seedUrl"`
	MaxDepth       int      `json:"maxDepth"`
	MaxPages       int      `json:"maxPages"`
	CollectionID   string   `json:"collectionId,omitempty"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}
