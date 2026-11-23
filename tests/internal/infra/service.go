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

const requestTimeout = 5 * time.Second

var httpClient = &http.Client{
	Timeout: requestTimeout,
}

// Dependencies are the local services the end-to-end suite runs against.
type Dependencies struct {
	MiniStack   Service
	RabbitMQ    Service
	OpenSearch  Service
	Gateway     Service
	Coordinator Service
	Capture     Service
	Search      Service
}

// Service is one dependency's observable health endpoint.
type Service struct {
	name      string
	baseURL   string
	healthURL string
	username  string
	password  string
}

// URL returns an absolute URL for a path on this service.
func (s Service) URL(path string) string {
	return s.baseURL + path
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

	baseURL := "http://" + net.JoinHostPort("localhost", mappedPort.Port())

	return Service{
		name:      name,
		baseURL:   baseURL,
		healthURL: baseURL + path,
		username:  username,
		password:  password,
	}
}
