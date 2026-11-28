// Package infra provides utilities for managing the infrastructure required for end-to-end tests.
package infra

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

var (
	startOnce    sync.Once
	shared       Dependencies
	startErr     error
	stack        *compose.DockerCompose
	terraformDir string
)

// Start returns a test-scoped environment backed by the shared stack, starting it on first use.
func Start(t *testing.T) TestEnv {
	t.Helper()

	startOnce.Do(func() {
		startErr = start()
	})

	require.NoError(t, startErr, "start e2e services")

	return newTestEnv(t, shared)
}

// Stop tears down the shared stack. Call it from TestMain after the suite completes.
func Stop() {
	if stack == nil {
		return
	}

	if err := stack.Down(context.Background(), compose.RemoveVolumes(true)); err != nil {
		fmt.Fprintf(os.Stderr, "stop e2e services: %v\n", err)
	}

	if terraformDir != "" {
		os.RemoveAll(terraformDir)
	}

	stack = nil
	terraformDir = ""
}

func start() error {
	ctx := context.Background()

	root, err := repositoryRoot()

	if err != nil {
		return err
	}

	terraformDir, err = prepareTerraform(root)

	if err != nil {
		return fmt.Errorf("prepare terraform: %w", err)
	}

	currentStack, err := newComposeStack(
		filepath.Join(root, "docker-compose.yaml"),
		filepath.Join(root, "tests", "compose.yaml"),
	)

	if err != nil {
		return err
	}

	stack = currentStack

	stackEnv, err := stackEnvironment(terraformDir)
	if err != nil {
		return fmt.Errorf("configure e2e ports: %w", err)
	}

	stack.WithEnv(stackEnv)

	if err = stack.Up(ctx); err != nil {
		return fmt.Errorf("start e2e services: %w", err)
	}

	services, err := resolveServices(ctx, stack)

	if err != nil {
		return err
	}

	captureWorkers, err := listServiceContainers(ctx, captureWorkerService)

	if err != nil {
		return err
	}

	services.CaptureWorkers = captureWorkers

	shared = services

	readinessCtx, cancel := context.WithTimeout(ctx, readinessTimeout)
	defer cancel()

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
		return fmt.Errorf("wait for e2e services to become healthy: %w", err)
	}

	if err := waitForContainerHealth(
		readinessCtx,
		captureWorkerService,
		captureWorkerReplicaCount,
	); err != nil {
		return fmt.Errorf("wait for capture worker replicas: %w", err)
	}

	if err := waitForQueueConsumers(
		readinessCtx,
		services.RabbitMQ,
		capturePageQueue,
		captureWorkerReplicaCount,
	); err != nil {
		return fmt.Errorf("wait for capture page consumers: %w", err)
	}

	return nil
}

func resolveServices(ctx context.Context, currentStack compose.ComposeStack) (Dependencies, error) {
	var dependencies Dependencies

	services := []struct {
		target   *Service
		name     string
		port     string
		path     string
		username string
		password string
	}{
		{&dependencies.MiniStack, ministackService, "4566", "/_ministack/health", "", ""},
		{&dependencies.RabbitMQ, rabbitMQService, "15672", "/api/overview", rabbitMQUsername, rabbitMQPassword},
		{&dependencies.OpenSearch, openSearchService, "9200", "/_cluster/health", "", ""},
		{&dependencies.Gateway, gatewayService, "8080", "/health/ready", "", ""},
		{&dependencies.Coordinator, coordinatorService, "8081", "/health/ready", "", ""},
		{&dependencies.Capture, captureWorkerService, "8000", "/health/ready", "", ""},
		{&dependencies.Search, searchService, "8082", "/health/ready", "", ""},
	}

	for _, service := range services {
		resolved, err := newService(
			ctx,
			currentStack,
			service.name,
			service.port,
			service.path,
			service.username,
			service.password,
		)

		if err != nil {
			return Dependencies{}, err
		}

		*service.target = resolved
	}

	return dependencies, nil
}
