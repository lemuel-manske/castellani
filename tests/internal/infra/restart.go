package infra

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

const (
	restartTimeout     = readinessTimeout
	serviceStopTimeout = 10 * time.Second
)

var restartMu sync.Mutex

// RestartService restarts a resolved service in place and waits for it to become healthy again.
func (e TestEnv) RestartService(t *testing.T, service Service) {
	t.Helper()

	e.WithServiceStopped(t, service, func() {})
}

// WithServiceStopped stops a service, runs during, and restores the service afterwards.
func (TestEnv) WithServiceStopped(t *testing.T, service Service, during func()) {
	t.Helper()

	restartMu.Lock()
	defer restartMu.Unlock()

	stopCtx, stopCancel := context.WithTimeout(context.Background(), restartTimeout)
	defer stopCancel()

	require.NoError(t, stopService(stopCtx, service), "stop %s", service.name)

	defer func() {
		startCtx, startCancel := context.WithTimeout(context.Background(), restartTimeout)
		defer startCancel()

		require.NoError(t, startService(startCtx, service), "start %s", service.name)
	}()

	during()
}

func stopService(ctx context.Context, service Service) error {
	containers, err := listServiceContainers(ctx, service.name)

	if err != nil {
		return fmt.Errorf("resolve %s for stop: %w", service.name, err)
	}

	if len(containers) == 0 {
		return fmt.Errorf("no %s containers found for stop", service.name)
	}

	for _, container := range containers {
		if err := container.Stop(ctx, serviceStopTimeout); err != nil {
			return fmt.Errorf("stop %s: %w", service.name, err)
		}
	}

	return nil
}

func startService(ctx context.Context, service Service) error {
	containers, err := listServiceContainers(ctx, service.name)

	if err != nil {
		return fmt.Errorf("resolve %s for start: %w", service.name, err)
	}

	if len(containers) == 0 {
		return fmt.Errorf("no %s containers found for start", service.name)
	}

	for _, container := range containers {
		if err = container.Start(ctx); err != nil {
			return fmt.Errorf("start %s: %w", service.name, err)
		}
	}

	restarted, err := newService(
		ctx,
		stack,
		service.name,
		string(service.port),
		service.healthPath,
		service.username,
		service.password,
	)

	if err != nil {
		return fmt.Errorf("resolve %s after restart: %w", service.name, err)
	}

	if restarted.baseURL != service.baseURL {
		return fmt.Errorf(
			"restart changed the published URL for %s: %s -> %s",
			service.name,
			service.baseURL,
			restarted.baseURL,
		)
	}

	return waitForHealthy(ctx, service)
}
