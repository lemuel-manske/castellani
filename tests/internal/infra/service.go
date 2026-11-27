package infra

import (
	"context"
	"net"
	"net/http"
	"testing"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

const requestTimeout = 5 * time.Second

var httpClient = &http.Client{
	Timeout: requestTimeout,
}

type Dependencies struct {
	MiniStack   Service
	RabbitMQ    Service
	OpenSearch  Service
	Gateway     Service
	Coordinator Service
	Capture     Service
	Search      Service
}

type Service struct {
	name      string
	baseURL   string
	healthURL string
	username  string
	password  string
}


func (s Service) BaseURL() string {
	return s.baseURL
}

func (s Service) URL(path string) string {
	return s.baseURL + path
}

func (s Service) HealthStatus(ctx context.Context) (int, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		s.healthURL,
		nil,
	)

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
