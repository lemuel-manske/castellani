package coordinator

const acceptedStatus = "ACCEPTED"

type Submission struct {
	SeedURL        string   `json:"seedUrl"`
	CollectionID   string   `json:"collectionId,omitempty"`
	MaxDepth       *int     `json:"maxDepth"`
	MaxPages       *int     `json:"maxPages"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}

type Accepted struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	StatusURL string `json:"statusUrl"`
}
