package infra

import (
	"context"
	"net"
	"net/http"
	"testing"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

const (
	readinessTimeout  = 120 * time.Second
	readinessInterval = 500 * time.Millisecond
	requestTimeout    = 5 * time.Second

	rabbitMQUsername = "castellani"
	rabbitMQPassword = "local-development-only"
)

var httpClient = &http.Client{Timeout: requestTimeout}

// Dependencies are the local services the end-to-end suite runs against.
type Dependencies struct {
	MiniStack  Service
	RabbitMQ   Service
	OpenSearch Service
}

// Service is one dependency's observable health endpoint.
type Service struct {
	healthURL string
	username  string
	password  string
}

// Start brings up the dependency stack and waits until every service answers
// its health check. The stack is torn down when the test finishes.
func Start(t *testing.T) Dependencies {
	t.Helper()

	ctx := context.Background()

	stack, err := compose.NewDockerComposeWith(compose.WithStackFiles("compose.yaml"))
	require.NoError(t, err)

	t.Cleanup(func() {
		require.NoError(t, stack.Down(context.Background()))
	})

	require.NoError(t, stack.Up(ctx))

	miniStack := newService(t, ctx, stack, "ministack", "4566", "/_ministack/health", "", "")
	rabbitMQ := newService(t, ctx, stack, "rabbitmq", "15672", "/api/overview", rabbitMQUsername, rabbitMQPassword)
	openSearch := newService(t, ctx, stack, "opensearch", "9200", "/_cluster/health", "", "")

	waitForHealthy(t, ctx, miniStack)
	waitForHealthy(t, ctx, rabbitMQ)
	waitForHealthy(t, ctx, openSearch)

	return Dependencies{
		MiniStack:  miniStack,
		RabbitMQ:   rabbitMQ,
		OpenSearch: openSearch,
	}
}

// HealthStatus performs the service's health request and reports its result.
func (s Service) HealthStatus(ctx context.Context) (int, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, s.healthURL, nil)
	if err != nil {
		return 0, err
	}

	if s.username != "" {
		request.SetBasicAuth(s.username, s.password)
	}

	response, err := httpClient.Do(request)
	if err != nil {
		return 0, err
	}
	defer response.Body.Close()

	return response.StatusCode, nil
}

func newService(
	t *testing.T,
	ctx context.Context,
	stack compose.ComposeStack,
	name string,
	port string,
	path string,
	username string,
	password string,
) Service {
	t.Helper()

	container, err := stack.ServiceContainer(ctx, name)
	require.NoError(t, err)

	mappedPort, err := container.MappedPort(ctx, nat.Port(port))
	require.NoError(t, err)

	return Service{
		healthURL: "http://" + net.JoinHostPort("localhost", mappedPort.Port()) + path,
		username:  username,
		password:  password,
	}
}

func waitForHealthy(t *testing.T, ctx context.Context, service Service) {
	t.Helper()

	deadline := time.Now().Add(readinessTimeout)
	ticker := time.NewTicker(readinessInterval)
	defer ticker.Stop()

	for {
		status, err := service.HealthStatus(ctx)
		if err == nil && status == http.StatusOK {
			return
		}

		if time.Now().After(deadline) {
			require.NoError(t, err)
			require.Equal(t, http.StatusOK, status)
			return
		}

		<-ticker.C
	}
}
