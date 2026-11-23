package infra

import (
	"context"
	"io"
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

// logServiceContainer writes a service's logs when Compose startup fails.
func logServiceContainer(t *testing.T, ctx context.Context, stack compose.ComposeStack, name string) {
	t.Helper()

	container, err := stack.ServiceContainer(ctx, name)
	if err != nil {
		t.Logf("%s container unavailable: %v", name, err)
		return
	}

	logs, err := container.Logs(ctx)
	if err != nil {
		t.Logf("%s logs unavailable: %v", name, err)
		return
	}
	defer logs.Close()

	contents, err := io.ReadAll(logs)
	if err != nil {
		t.Logf("read %s logs: %v", name, err)
		return
	}

	t.Logf("%s container logs:\n%s", name, contents)
}
