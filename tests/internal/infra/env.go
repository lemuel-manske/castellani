package infra

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

type TestEnv struct {
	Dependencies
	runID string
}

func newTestEnv(t *testing.T, dependencies Dependencies) TestEnv {
	t.Helper()

	env := TestEnv{
		Dependencies: dependencies,
		runID:        newRunID(t),
	}

	t.Cleanup(func() {
		env.cleanup(t)
	})

	return env
}

func (e TestEnv) IdempotencyKey(name string) string {
	return e.runID + "-" + name
}

func (e TestEnv) cleanup(t *testing.T) {
	t.Helper()

	ctx, cancel := context.WithTimeout(context.Background(), cleanupRequestTimeout)
	defer cancel()

	require.NoError(
		t,
		cleanupTestArchives(ctx, e.Dependencies, e.runID),
		"clean up test %s",
		e.runID,
	)
}

func newRunID(t *testing.T) string {
	t.Helper()

	var suffix [8]byte

	_, err := rand.Read(suffix[:])
	require.NoError(t, err)

	name := strings.Map(func(r rune) rune {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9', r == '-', r == '_':
			return r
		default:
			return '-'
		}
	}, t.Name())

	return name + "-" + hex.EncodeToString(suffix[:])
}
