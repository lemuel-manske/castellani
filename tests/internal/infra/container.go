package infra

import (
	"context"
	"fmt"
	"time"

	dockertypes "github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/client"
)

const (
	composeProjectLabel = "com.docker.compose.project"
	composeServiceLabel = "com.docker.compose.service"

	containerHealthy = "healthy"
)

type Container struct {
	service string
	id      string
}

func (c Container) ID() string {
	return c.id
}

func (c Container) HealthStatus(ctx context.Context) (string, error) {
	dockerClient, err := newDockerClient()

	if err != nil {
		return "", err
	}

	defer dockerClient.Close()

	inspect, err := dockerClient.ContainerInspect(ctx, c.id)

	if err != nil {
		return "", fmt.Errorf(
			"inspect %s: %w",
			c.service,
			err,
		)
	}

	if inspect.State == nil || inspect.State.Health == nil {
		return "", fmt.Errorf("%s has no health status", c.service)
	}

	return inspect.State.Health.Status, nil
}

func (c Container) Stop(ctx context.Context, timeout time.Duration) error {
	dockerClient, err := newDockerClient()

	if err != nil {
		return err
	}

	defer dockerClient.Close()

	seconds := int(timeout / time.Second)

	return dockerClient.ContainerStop(
		ctx,
		c.id,
		dockertypes.StopOptions{
		Timeout: &seconds,
	},
	)
}

func (c Container) Start(ctx context.Context) error {
	dockerClient, err := newDockerClient()

	if err != nil {
		return err
	}

	defer dockerClient.Close()

	return dockerClient.ContainerStart(
		ctx,
		c.id,
		dockertypes.StartOptions{},
	)
}

func listServiceContainers(ctx context.Context, service string) ([]Container, error) {
	dockerClient, err := newDockerClient()

	if err != nil {
		return nil, err
	}

	defer dockerClient.Close()

	summaries, err := dockerClient.ContainerList(ctx, dockertypes.ListOptions{
		All: true,
		Filters: filters.NewArgs(
			filters.Arg("label", composeProjectLabel+"="+e2eProjectName),
			filters.Arg("label", composeServiceLabel+"="+service),
		),
	})

	if err != nil {
		return nil, fmt.Errorf(
			"list %s containers: %w",
			service,
			err,
		)
	}

	containers := make(
		[]Container,
		0,
		len(summaries),
	)

	for _, summary := range summaries {
		containers = append(containers, Container{
			service: service,
			id:      summary.ID,
		})
	}

	return containers, nil
}

func waitForContainerHealth(
	ctx context.Context,
	service string,
	count int,
) error {
	ticker := time.NewTicker(readinessInterval)
	defer ticker.Stop()

	var lastErr error

	for {
		containers, err := listServiceContainers(ctx, service)

		if err != nil {
			lastErr = err
		} else if len(containers) != count {
			lastErr = fmt.Errorf(
				"found %d %s containers; want %d",
				len(containers),
				service,
				count,
			)
		} else {
			lastErr = requireHealthyContainers(
				ctx,
				containers,
				count,
			)
		}

		if lastErr == nil {
			return nil
		}

		select {
		case <-ctx.Done():
			return fmt.Errorf(
				"wait for %s replicas: %w; last error: %v",
				service,
				ctx.Err(),
				lastErr,
			)
		case <-ticker.C:
		}
	}
}

func requireHealthyContainers(
	ctx context.Context,
	containers []Container,
	count int,
) error {
	healthyCount := 0

	for _, container := range containers {
		status, err := container.HealthStatus(ctx)

		if err != nil {
			return err
		}

		if status == containerHealthy {
			healthyCount++
		}
	}

	if healthyCount != count {
		return fmt.Errorf(
			"%d/%d containers are healthy",
			healthyCount,
			count,
		)
	}

	return nil
}

func newDockerClient() (*client.Client, error) {
	dockerClient, err := client.NewClientWithOpts(
		client.FromEnv,
		client.WithAPIVersionNegotiation(),
	)

	if err != nil {
		return nil, fmt.Errorf("create docker client: %w", err)
	}

	return dockerClient, nil
}
