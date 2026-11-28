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
func (TestEnv) RestartService(t *testing.T, service Service) {
	t.Helper()

	ctx, cancel := context.WithTimeout(context.Background(), restartTimeout)
	defer cancel()

	require.NoError(t, restartService(ctx, service), "restart %s", service.name)
}

func restartService(ctx context.Context, service Service) error {
	restartMu.Lock()
	defer restartMu.Unlock()

	container, err := stack.ServiceContainer(ctx, service.name)

	if err != nil {
		return fmt.Errorf("resolve %s for restart: %w", service.name, err)
	}

	stopTimeout := serviceStopTimeout

	if err = container.Stop(ctx, &stopTimeout); err != nil {
		return fmt.Errorf("stop %s: %w", service.name, err)
	}

	if err = container.Start(ctx); err != nil {
		return fmt.Errorf("start %s: %w", service.name, err)
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
