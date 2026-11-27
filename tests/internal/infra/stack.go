// Package infra provides utilities for managing the infrastructure required for end-to-end tests.
package infra

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

var (
	startMu sync.Mutex
	shared  *Dependencies
	stack   *compose.DockerCompose
)

// Start returns the shared stack, starting it on first use and resetting it after each test.
func Start(t *testing.T) Dependencies {
	t.Helper()

	startMu.Lock()
	defer startMu.Unlock()

	if shared == nil {
		dependencies := start(t)
		shared = &dependencies
	}

	t.Cleanup(func() {
		shared.Reset(t)
	})

	return *shared
}

// Stop tears down the shared stack. Call it from TestMain after the suite completes.
func Stop() {
	if stack == nil {
		return
	}

	if err := stack.Down(context.Background(), compose.RemoveVolumes(true)); err != nil {
		fmt.Fprintf(
			os.Stderr,
			"stop e2e services: %v\n",
			err,
		)
	}

	stack = nil
}

func start(t *testing.T) Dependencies {
	t.Helper()

	ctx := context.Background()

	root := repositoryRoot(t)

	terraformDir := prepareTerraform(t, root)

	stack = newComposeStack(
		t,
		filepath.Join(root, "docker-compose.yaml"),
		filepath.Join(
			root,
			"tests",
			"compose.yaml",
		),
	)

	stack.WithEnv(stackEnvironment(terraformDir))

	if err := stack.Up(ctx); err != nil {
		require.NoError(
			t,
			err,
			"start e2e services",
		)
	}

	services := Dependencies{
		MiniStack: newService(
			t,
			ctx,
			stack,
			"ministack",
			"4566",
			"/_ministack/health",
			"",
			"",
		),
		RabbitMQ: newService(
			t,
			ctx,
			stack,
			"rabbitmq",
			"15672",
			"/api/overview",
			rabbitMQUsername,
			rabbitMQPassword,
		),
		OpenSearch: newService(
			t,
			ctx,
			stack,
			"opensearch",
			"9200",
			"/_cluster/health",
			"",
			"",
		),
		Gateway: newService(
			t,
			ctx,
			stack,
			"gateway",
			"8080",
			"/health/ready",
			"",
			"",
		),
		Coordinator: newService(
			t,
			ctx,
			stack,
			"coordinator",
			"8081",
			"/health/ready",
			"",
			"",
		),
		Capture: newService(
			t,
			ctx,
			stack,
			"capture-worker",
			"8000",
			"/health/ready",
			"",
			"",
		),
		Search: newService(
			t,
			ctx,
			stack,
			"search",
			"8082",
			"/health/ready",
			"",
			"",
		),
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
		require.NoError(
			t,
			err,
			"wait for e2e services to become healthy",
		)
	}

	t.Logf("service readiness: %s", time.Since(readinessStarted))

	return services
}
