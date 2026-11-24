// Package infra provides utilities for managing the infrastructure required for end-to-end tests.
package infra

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

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

	if err := stack.Up(ctx); err != nil {
		require.NoError(t, err, "start e2e services")
	}

	services := Dependencies{
		MiniStack:   newService(t, ctx, stack, "ministack", "4566", "/_ministack/health", "", ""),
		RabbitMQ:    newService(t, ctx, stack, "rabbitmq", "15672", "/api/overview", rabbitMQUsername, rabbitMQPassword),
		OpenSearch:  newService(t, ctx, stack, "opensearch", "9200", "/_cluster/health", "", ""),
		Gateway:     newService(t, ctx, stack, "gateway", "8080", "/health/ready", "", ""),
		Coordinator: newService(t, ctx, stack, "coordinator", "8081", "/health/ready", "", ""),
		Capture:     newService(t, ctx, stack, "capture-worker", "8000", "/health/ready", "", ""),
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
		require.NoError(t, err, "wait for e2e services to become healthy")
	}

	t.Logf("service readiness: %s", time.Since(readinessStarted))

	return services
}
