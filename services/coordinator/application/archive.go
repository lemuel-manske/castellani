package application

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/lemuel-manske/unnamed/services/coordinator/internal/archive"
)

var (
	ErrConflict = errors.New("idempotency key belongs to a different request")
	ErrNotFound = errors.New("archive not found")
	ErrInvalid  = errors.New("invalid archive")
)

type Store interface {
	Admit(context.Context, string, string, archive.AcceptedResponse, archive.Submission, time.Time) (archive.AcceptedResponse, error)
	Status(context.Context, string) (archive.Status, error)
}

type Service struct {
	store Store
	now   func() time.Time
}

func New(store Store) Service { return Service{store: store, now: time.Now} }

func (s Service) Create(ctx context.Context, key string, submission archive.Submission) (archive.AcceptedResponse, error) {
	if err := submission.Validate(); err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	raw, err := submission.Canonical()
	if err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("canonicalize submission: %w", err)
	}
	var random [16]byte
	if _, err := rand.Read(random[:]); err != nil {
		return archive.AcceptedResponse{}, fmt.Errorf("generate archive ID: %w", err)
	}
	id := hex.EncodeToString(random[:])
	accepted := archive.AcceptedResponse{ArchiveID: id, Status: archive.Accepted, StatusURL: "/archives/" + id}
	return s.store.Admit(ctx, key, archive.Digest(raw), accepted, submission, s.now().UTC())
}

func (s Service) Get(ctx context.Context, id string) (archive.Status, error) {
	if !archive.ValidID(id) {
		return archive.Status{}, ErrNotFound
	}
	return s.store.Status(ctx, id)
}
