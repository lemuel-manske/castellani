package infra

import (
	"context"
	"testing"
	"time"

	"github.com/docker/docker/client"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

const dockerCheckTimeout = 5 * time.Second

func checkDockerDaemon(ctx context.Context) error {
	dockerClient, err := client.NewClientWithOpts(client.FromEnv)
	if err != nil {
		return err
	}

	defer dockerClient.Close()

	_, err = dockerClient.Ping(ctx)

	return err
}

func newComposeStack(t *testing.T, composeFile string) *compose.DockerCompose {
	t.Helper()

	ctx, cancel := context.WithTimeout(context.Background(), dockerCheckTimeout)
	defer cancel()

	require.NoError(t, checkDockerDaemon(ctx), "Docker must be running to execute the e2e suite")

	var (
		stack *compose.DockerCompose
		err   error
	)

	require.NotPanics(t, func() {
		stack, err = compose.NewDockerComposeWith(compose.WithStackFiles(composeFile))
	}, "Docker must be running to execute the e2e suite")

	require.NoError(t, err)

	return stack
}
