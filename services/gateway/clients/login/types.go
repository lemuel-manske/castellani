package login

import (
	"errors"
	"fmt"
)

var (
	ErrInvalidResponse = errors.New("invalid capture response")
	ErrUnavailable     = errors.New("capture unavailable")
)

type Failure struct {
	Status       int
	Type         string
	Title        string
	Detail       string
	ContentRange string
}

func (f *Failure) Error() string {
	return fmt.Sprintf(
		"login returned HTTP %d: %s",
		f.Status,
		f.Title,
	)
}

type SessionRequest struct {
	ArchiveID, TargetURL string
}

type Session struct {
	SessionID      string `json:"sessionId"`
	ArchiveID      string `json:"archiveId"`
	Status         string `json:"status"`
	ExpiresAt      string `json:"expiresAt"`
	AuthGeneration *int   `json:"authGeneration,omitempty"`
}
