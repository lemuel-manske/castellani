package coordinator

import (
	"fmt"
)

const acceptedStatus = "ACCEPTED"

type Failure struct {
	Status int
	Type   string
	Title  string
	Detail string
}

func (f *Failure) Error() string {
	return fmt.Sprintf("coordinator returned HTTP %d", f.Status)
}

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
