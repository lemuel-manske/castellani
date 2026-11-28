package infra

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/testcontainers/testcontainers-go/modules/compose"
)

const requestTimeout = 5 * time.Second

var httpClient = &http.Client{
	Timeout: requestTimeout,
}

type Dependencies struct {
	MiniStack      Service
	RabbitMQ       Service
	OpenSearch     Service
	Gateway        Service
	Coordinator    Service
	Capture        Service
	CaptureWorkers []Container
	Search         Service
}

type Service struct {
	name       string
	baseURL    string
	healthURL  string
	healthPath string
	port       nat.Port
	username   string
	password   string
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
	ctx context.Context,
	stack compose.ComposeStack,
	name string,
	port string,
	path string,
	username string,
	password string,
) (Service, error) {
	container, err := stack.ServiceContainer(ctx, name)

	if err != nil {
		return Service{}, fmt.Errorf(
			"resolve service %s: %w",
			name,
			err,
		)
	}

	mappedPort, err := container.MappedPort(ctx, nat.Port(port))

	if err != nil {
		return Service{}, fmt.Errorf(
			"resolve port %s for %s: %w",
			port,
			name,
			err,
		)
	}

	baseURL := "http://" + net.JoinHostPort("localhost", mappedPort.Port())

	return Service{
		name:       name,
		baseURL:    baseURL,
		healthURL:  baseURL + path,
		healthPath: path,
		port:       nat.Port(port),
		username:   username,
		password:   password,
	}, nil
}
