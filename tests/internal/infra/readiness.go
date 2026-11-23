package infra

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"
)

const (
	readinessTimeout  = 120 * time.Second
	readinessInterval = 500 * time.Millisecond
)

func waitForAllHealthy(ctx context.Context, services ...Service) error {
	var (
		group sync.WaitGroup
		errs  = make(chan error, len(services))
	)

	for _, service := range services {
		group.Go(func() {
			if err := waitForHealthy(ctx, service); err != nil {
				errs <- err
			}
		})
	}

	group.Wait()
	close(errs)

	var failures []error
	for err := range errs {
		failures = append(failures, err)
	}

	return errors.Join(failures...)
}

func waitForHealthy(ctx context.Context, service Service) error {
	ticker := time.NewTicker(readinessInterval)
	defer ticker.Stop()

	var (
		status  int
		lastErr error
	)

	for {
		status, lastErr = service.HealthStatus(ctx)
		if lastErr == nil && status == http.StatusOK {
			return nil
		}

		select {
		case <-ctx.Done():
			return fmt.Errorf(
				"%s did not become healthy: %w (last status: %d, last error: %v)",
				service.name,
				ctx.Err(),
				status,
				lastErr,
			)
		case <-ticker.C:
		}
	}
}
