package infra

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

// Start brings up the full stack and waits until every service answers its
// health check. The stack is torn down when the test finishes.
func Start(t *testing.T) Dependencies {
	t.Helper()

	ctx := context.Background()
	root := repositoryRoot(t)
	terraformDir := prepareTerraform(t, root)
	stack := newComposeStack(t, filepath.Join(root, "docker-compose.yaml"))

	stack.WithEnv(stackEnvironment(terraformDir))

	t.Cleanup(func() {
		require.NoError(t, stack.Down(context.Background(), compose.RemoveVolumes(true)))
	})

	// Start Compose before looking up its service containers.
	if err := stack.Up(ctx); err != nil {
		logServices(t, ctx, stack)
		require.NoError(t, err, "start e2e services")
	}

	services := Dependencies{
		MiniStack:   newService(t, ctx, stack, "ministack", "4566", "/_ministack/health", "", ""),
		RabbitMQ:    newService(t, ctx, stack, "rabbitmq", "15672", "/api/overview", rabbitMQUsername, rabbitMQPassword),
		OpenSearch:  newService(t, ctx, stack, "opensearch", "9200", "/_cluster/health", "", ""),
		Gateway:     newService(t, ctx, stack, "gateway", "8080", "/health/ready", "", ""),
		Coordinator: newService(t, ctx, stack, "coordinator", "8081", "/health/ready", "", ""),
		Capture:     newService(t, ctx, stack, "capture", "8000", "/health/ready", "", ""),
		Search:      newService(t, ctx, stack, "search", "8082", "/health/ready", "", ""),
	}

	readinessCtx, cancel := context.WithTimeout(ctx, readinessTimeout)
	defer cancel()

	readinessStarted := time.Now()
	if err := waitForAllHealthy(
		readinessCtx,
		services.MiniStack,
		services.RabbitMQ,
		services.OpenSearch,
		services.Gateway,
		services.Coordinator,
		services.Capture,
		services.Search,
	); err != nil {
		logServices(t, context.Background(), stack)
		require.NoError(t, err, "wait for e2e services to become healthy")
	}

	t.Logf("service readiness: %s", time.Since(readinessStarted))

	return services
}

func logServices(t *testing.T, ctx context.Context, stack compose.ComposeStack) {
	t.Helper()

	for _, name := range []string{
		"provision",
		"ministack",
		"rabbitmq",
		"opensearch",
		"coordinator",
		"capture",
		"search",
		"gateway",
	} {
		logServiceContainer(t, ctx, stack, name)
	}
}
