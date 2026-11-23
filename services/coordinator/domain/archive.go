// Package domain defines the core boundaries of the Coordinator service.
package domain

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"time"

	"github.com/lemuel-manske/castellani/libs/httpx"
)

const (
	StatusAccepted            = "ACCEPTED"
	StatusRunning             = "RUNNING"
	StatusFinalizing          = "FINALIZING"
	StatusCompensating        = "COMPENSATING"
	StatusCompleted           = "COMPLETED"
	StatusCompletedWithErrors = "COMPLETED_WITH_ERRORS"
	StatusFailed              = "FAILED"

	DecisionNone = "NONE"

	ReplayNotReady = "NOT_READY"
	SearchPending  = "PENDING"
)

type Submission struct {
	SeedURL        string
	CollectionID   string
	MaxDepth       *int
	MaxPages       *int
	AllowedOrigins []string
	AuthGeneration *int
}

type ValidationError struct {
	Field   string
	Message string
}

func (e ValidationError) Error() string {
	return e.Field + " " + e.Message
}

func (s Submission) Fingerprint() (string, error) {
	if s.MaxDepth == nil || s.MaxPages == nil {
		return "", errors.New("cannot fingerprint an invalid submission")
	}

	origins := append([]string(nil), s.AllowedOrigins...)

	sort.Strings(origins)

	payload := struct {
		SeedURL        string   `json:"seedUrl"`
		CollectionID   string   `json:"collectionId,omitempty"`
		MaxDepth       int      `json:"maxDepth"`
		MaxPages       int      `json:"maxPages"`
		AllowedOrigins []string `json:"allowedOrigins,omitempty"`
		AuthGeneration *int     `json:"authGeneration,omitempty"`
	}{
		SeedURL:        s.SeedURL,
		CollectionID:   s.CollectionID,
		MaxDepth:       *s.MaxDepth,
		MaxPages:       *s.MaxPages,
		AllowedOrigins: origins,
		AuthGeneration: s.AuthGeneration,
	}

	data, err := json.Marshal(payload)

	if err != nil {
		return "", err
	}

	digest := sha256.Sum256(data)

	return hex.EncodeToString(digest[:]), nil
}

type CaptureProgress struct {
	Captured int
	Failed   int
	Pending  int
}

type ReplayProgress struct {
	Status string
}

type SearchProgress struct {
	Status   string
	Indexed  int
	Expected int
}

type Archive struct {
	ID                     string
	Status                 string
	Capture                CaptureProgress
	Replay                 ReplayProgress
	Search                 SearchProgress
	Revision               int
	UpdatedAt              time.Time
	Decision               string
	DecisionVersion        int
	CrawlTerminal          bool
	SeedSucceeded          bool
	ManifestDigest         string
	PreparedManifestDigest string
	PackageDigest          string
	CaptureCompensated     bool
	SearchCompensated      bool
}

func (s Submission) Validate() error {
	if !httpx.ValidHTTPURL(s.SeedURL) {
		return ValidationError{
			Field:   "seedUrl",
			Message: "must be an absolute HTTP(S) URL without credentials or fragment",
		}
	}

	if s.MaxDepth == nil || *s.MaxDepth < 0 {
		return ValidationError{
			Field:   "maxDepth",
			Message: "must be a nonnegative integer",
		}
	}

	if s.MaxPages == nil || *s.MaxPages < 1 {
		return ValidationError{
			Field:   "maxPages",
			Message: "must be a positive integer",
		}
	}

	if s.AuthGeneration != nil && *s.AuthGeneration < 1 {
		return ValidationError{
			Field:   "authGeneration",
			Message: "must be a positive integer",
		}
	}

	seen := make(map[string]struct{}, len(s.AllowedOrigins))

	for _, origin := range s.AllowedOrigins {
		if !httpx.ValidHTTPURL(origin) {
			return ValidationError{
				Field:   "allowedOrigins",
				Message: "entries must be absolute HTTP(S) URLs without credentials or fragment",
			}
		}

		if _, exists := seen[origin]; exists {
			return ValidationError{
				Field:   "allowedOrigins",
				Message: "entries must be unique",
			}
		}

		seen[origin] = struct{}{}
	}

	return nil
}
