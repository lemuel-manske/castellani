package archive

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/url"
	"strings"
)

const (
	Accepted            = "ACCEPTED"
	Running             = "RUNNING"
	Finalizing          = "FINALIZING"
	Compensating        = "COMPENSATING"
	Completed           = "COMPLETED"
	CompletedWithErrors = "COMPLETED_WITH_ERRORS"
	Failed              = "FAILED"
)

type Submission struct {
	SeedURL        string   `json:"seedUrl"`
	CollectionID   string   `json:"collectionId,omitempty"`
	MaxDepth       *int     `json:"maxDepth"`
	MaxPages       *int     `json:"maxPages"`
	AllowedOrigins []string `json:"allowedOrigins,omitempty"`
	AuthGeneration *int     `json:"authGeneration,omitempty"`
}

type AcceptedResponse struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	StatusURL string `json:"statusUrl"`
}

type Counts struct {
	Captured int `json:"captured"`
	Failed   int `json:"failed"`
	Pending  int `json:"pending"`
}

type Replay struct {
	Status string `json:"status"`
}

type Search struct {
	Status   string `json:"status"`
	Indexed  int    `json:"indexed"`
	Expected int    `json:"expected"`
}

type Status struct {
	ArchiveID string `json:"archiveId"`
	Status    string `json:"status"`
	Capture   Counts `json:"capture"`
	Replay    Replay `json:"replay"`
	Search    Search `json:"search"`
}

func (s Submission) Validate() error {
	if !validURL(s.SeedURL) {
		return errors.New("seedUrl must be an absolute HTTP(S) URL without credentials or fragment")
	}

	if s.MaxDepth == nil || *s.MaxDepth < 0 {
		return errors.New("maxDepth must be a nonnegative integer")
	}

	if s.MaxPages == nil || *s.MaxPages < 1 {
		return errors.New("maxPages must be a positive integer")
	}

	if s.AuthGeneration != nil && *s.AuthGeneration < 1 {
		return errors.New("authGeneration must be positive")
	}

	seen := make(map[string]bool, len(s.AllowedOrigins))

	for _, origin := range s.AllowedOrigins {
		invalidOrigin := !validURL(origin)
		duplicateOrigin := seen[origin]

		if invalidOrigin || duplicateOrigin {
			return errors.New("allowedOrigins must contain unique absolute HTTP(S) URLs")
		}

		seen[origin] = true
	}

	return nil
}

func (s Submission) Canonical() ([]byte, error) {
	// Absent and empty optional origins have the same request identity.
	if s.AllowedOrigins == nil {
		s.AllowedOrigins = []string{}
	}

	return json.Marshal(s)
}

func Digest(canonical []byte) string {
	sum := sha256.Sum256(canonical)
	return hex.EncodeToString(sum[:])
}

func ValidID(id string) bool {
	reserved := id == "" || id == "." || id == ".."
	hasSeparator := strings.ContainsAny(id, "/\\")

	return !reserved && !hasSeparator
}

func validURL(raw string) bool {
	parsed, err := url.Parse(raw)

	if err != nil {
		return false
	}

	httpScheme := parsed.Scheme == "http" || parsed.Scheme == "https"
	hasHostname := parsed.Hostname() != ""
	noCredentials := parsed.User == nil
	noFragment := parsed.Fragment == ""

	return httpScheme && hasHostname && noCredentials && noFragment
}
