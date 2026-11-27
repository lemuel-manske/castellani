// Package infra provides utilities for managing the infrastructure required for end-to-end tests.
package infra

import (
	"context"
	"fmt"
	"io"
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
		dumpServiceLogs(t, ctx, stack,
			"ministack",
			"rabbitmq",
			"opensearch",
			"provision",
			"coordinator",
			"capture-worker",
			"capture-login",
			"search",
			"gateway",
		)
		require.NoError(t, err, "start e2e services")
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

// dumpServiceLogs captures logs from containers that Compose created before startup failed.
func dumpServiceLogs(t *testing.T, ctx context.Context, stack *compose.DockerCompose, names ...string) {
	t.Helper()

	for _, name := range names {
		container, err := stack.ServiceContainer(ctx, name)
		if err != nil {
			t.Logf("%s container unavailable: %v", name, err)
			continue
		}

		reader, err := container.Logs(ctx)
		if err != nil {
			t.Logf("%s logs unavailable: %v", name, err)
			continue
		}

		content, readErr := io.ReadAll(reader)
		closeErr := reader.Close()
		if readErr != nil {
			t.Logf("%s logs could not be read: %v", name, readErr)
			continue
		}
		if closeErr != nil {
			t.Logf("%s log stream could not be closed: %v", name, closeErr)
		}

		const maxLogBytes = 64 * 1024
		if len(content) > maxLogBytes {
			content = content[len(content)-maxLogBytes:]
		}

		t.Logf("%s container logs (last 64 KiB):\n%s", name, content)
	}
}
