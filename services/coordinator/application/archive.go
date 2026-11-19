package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"

	"github.com/lemuel-manske/castellani/libs/httpx"
	"github.com/lemuel-manske/unnamed/services/coordinator/domain"
)

func (a *Application) SubmitArchive(
	ctx context.Context,
	key string,
	submission domain.Submission,
) (AcceptedArchive, error) {
	if !httpx.ValidIdempotencyKey(key) {
		return AcceptedArchive{}, ErrInvalidIdempotencyKey
	}

	if err := submission.Validate(); err != nil {
		return AcceptedArchive{}, errors.Join(ErrInvalidSubmission, err)
	}

	fingerprint, err := fingerprintSubmission(submission)

	if err != nil {
		return AcceptedArchive{}, err
	}

	admission := Admission{
		Key:         key,
		Fingerprint: fingerprint,
		Submission:  submission,
	}

	return a.archives.Admit(ctx, admission)
}

func (a *Application) GetArchive(ctx context.Context, id string) (domain.Archive, error) {
	if !httpx.ValidPathSegment(id) {
		return domain.Archive{}, ErrInvalidArchiveID
	}

	return a.archives.Find(ctx, id)
}

func fingerprintSubmission(submission domain.Submission) (string, error) {
	origins := append([]string(nil), submission.AllowedOrigins...)
	sort.Strings(origins)

	payload := struct {
		SeedURL        string   `json:"seedUrl"`
		CollectionID   string   `json:"collectionId,omitempty"`
		MaxDepth       int      `json:"maxDepth"`
		MaxPages       int      `json:"maxPages"`
		AllowedOrigins []string `json:"allowedOrigins,omitempty"`
		AuthGeneration *int     `json:"authGeneration,omitempty"`
	}{
		SeedURL:        submission.SeedURL,
		CollectionID:   submission.CollectionID,
		MaxDepth:       *submission.MaxDepth,
		MaxPages:       *submission.MaxPages,
		AllowedOrigins: origins,
		AuthGeneration: submission.AuthGeneration,
	}

	data, err := json.Marshal(payload)

	if err != nil {
		return "", err
	}

	digest := sha256.Sum256(data)

	return hex.EncodeToString(digest[:]), nil
}
