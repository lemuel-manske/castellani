package infra

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestCheckDockerDaemon_FailsFast(t *testing.T) {
	t.Setenv("DOCKER_HOST", "tcp://127.0.0.1:1")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	started := time.Now()

	err := checkDockerDaemon(ctx)

	require.Error(t, err)
	require.Less(t, time.Since(started), 10*time.Second)
}
