// Package domain defines the core boundaries of the Coordinator service.
package domain

import (
	"errors"
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
