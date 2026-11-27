package testutil

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func Eventually[T any](
	t *testing.T,
	timeout time.Duration,
	interval time.Duration,
	condition func() (T, bool),
	message string,
	args ...any,
) T {
	t.Helper()

	var value T

	require.Eventually(
		t,
		func() bool {
			var ready bool
			value, ready = condition()
			return ready
		},
		timeout,
		interval,
		message,
		args...,
	)

	return value
}

