package infra

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

func newComposeStack(t *testing.T, composeFile string) *compose.DockerCompose {
	t.Helper()

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
