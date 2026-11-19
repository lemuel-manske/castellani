// Package archive provides data structures for archive manipulation.
package archive

import (
	"errors"
	"github.com/lemuel-manske/castellani/libs/httpx"
)

const AcceptedStatus = "ACCEPTED"

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

func (s Submission) Validate() error {
	if !httpx.ValidHTTPURL(s.SeedURL) {
		return errors.New("seedUrl must be an absolute HTTP(S) URL without credentials or fragment")
	}

	if s.MaxDepth == nil || *s.MaxDepth < 0 {
		return errors.New("maxDepth must be a nonnegative integer")
	}

	if s.MaxPages == nil || *s.MaxPages < 1 {
		return errors.New("maxPages must be a positive integer")
	}

	if s.AuthGeneration != nil && *s.AuthGeneration < 1 {
		return errors.New("authGeneration must be a positive integer")
	}

	seen := make(map[string]struct{}, len(s.AllowedOrigins))
	for _, origin := range s.AllowedOrigins {
		if !httpx.ValidHTTPURL(origin) {
			return errors.New("allowedOrigins entries must be absolute HTTP(S) URLs without credentials or fragment")
		}

		if _, exists := seen[origin]; exists {
			return errors.New("allowedOrigins entries must be unique")
		}
		seen[origin] = struct{}{}
	}

	return nil
}
