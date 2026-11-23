package infra

import (
	"context"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
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

	terraformLockFile = ".terraform.lock.hcl"
)

var httpClient = &http.Client{
	Timeout: requestTimeout,
}

func repositoryRoot(t *testing.T) string {
	t.Helper()

	_, file, _, ok := runtime.Caller(0)
	require.True(
		t,
		ok,
		"locate repository root",
	)

	return filepath.Join(
		filepath.Dir(file),
		"..",
		"..",
		"..",
	)
}

func prepareTerraform(t *testing.T, root string) string {
	t.Helper()

	source := filepath.Join(
		root,
		"infra",
		"terraform",
	)
	target := t.TempDir()

	entries, err := os.ReadDir(source)
	require.NoError(t, err)

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		name := entry.Name()

		if !strings.HasSuffix(name, ".tf") && name != terraformLockFile {
			continue
		}

		contents, err := os.ReadFile(filepath.Join(source, name))
		require.NoError(t, err)

		require.NoError(
			t,
			os.WriteFile(
				filepath.Join(target, name),
				contents,
				0o600,
			),
		)
	}

	return target
}

func newComposeStack(t *testing.T, composeFile string) *compose.DockerCompose {
	t.Helper()

	var (
		stack *compose.DockerCompose
		err   error
	)

	require.NotPanics(
		t,
		func() {
			stack, err = compose.NewDockerComposeWith(
				compose.WithStackFiles(composeFile),
			)
		},
		"Docker must be running to execute the e2e suite",
	)

	require.NoError(t, err)

	return stack
}

func stackEnvironment(t *testing.T, terraformDir string) map[string]string {
	t.Helper()

	return map[string]string{
		"TERRAFORM_DIR":            terraformDir,
		"MINISTACK_PORT":           "0",
		"RABBITMQ_PORT":            "0",
		"RABBITMQ_MANAGEMENT_PORT": "0",
		"OPENSEARCH_PORT":          "0",
		"GATEWAY_PORT":             "0",
		"COORDINATOR_PORT":         "0",
		"CAPTURE_PORT":             "0",
		"SEARCH_PORT":              "0",
	}
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
	healthURL string
	username  string
	password  string
}

// Start brings up the full stack and waits until every service answers its
// health check. The stack is torn down when the test finishes.
func Start(t *testing.T) Dependencies {
	t.Helper()

	ctx := context.Background()

	root := repositoryRoot(t)
	terraformDir := prepareTerraform(t, root)
	stack := newComposeStack(t, filepath.Join(root, "docker-compose.yaml"))

	stack.WithEnv(stackEnvironment(t, terraformDir))

	t.Cleanup(func() {
		require.NoError(
			t,
			stack.Down(context.Background(), compose.RemoveVolumes(true)),
		)
	})

	require.NoError(t, stack.Up(ctx))

	miniStack := newService(
		t,
		ctx,
		stack,
		"ministack",
		"4566",
		"/_ministack/health",
		"",
		"",
	)
	rabbitMQ := newService(
		t,
		ctx,
		stack,
		"rabbitmq",
		"15672",
		"/api/overview",
		rabbitMQUsername,
		rabbitMQPassword,
	)
	openSearch := newService(
		t,
		ctx,
		stack,
		"opensearch",
		"9200",
		"/_cluster/health",
		"",
		"",
	)
	gateway := newService(
		t,
		ctx,
		stack,
		"gateway",
		"8080",
		"/health/ready",
		"",
		"",
	)
	coordinator := newService(
		t,
		ctx,
		stack,
		"coordinator",
		"8081",
		"/health/ready",
		"",
		"",
	)
	capture := newService(
		t,
		ctx,
		stack,
		"capture",
		"8000",
		"/health/ready",
		"",
		"",
	)
	search := newService(
		t,
		ctx,
		stack,
		"search",
		"8082",
		"/health/ready",
		"",
		"",
	)

	waitForHealthy(
		t,
		ctx,
		miniStack,
	)
	waitForHealthy(
		t,
		ctx,
		rabbitMQ,
	)
	waitForHealthy(
		t,
		ctx,
		openSearch,
	)
	waitForHealthy(
		t,
		ctx,
		gateway,
	)
	waitForHealthy(
		t,
		ctx,
		coordinator,
	)
	waitForHealthy(
		t,
		ctx,
		capture,
	)
	waitForHealthy(
		t,
		ctx,
		search,
	)

	return Dependencies{
		MiniStack:   miniStack,
		RabbitMQ:    rabbitMQ,
		OpenSearch:  openSearch,
		Gateway:     gateway,
		Coordinator: coordinator,
		Capture:     capture,
		Search:      search,
	}
}

// HealthStatus performs the service's health request and reports its result.
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

	return Service{
		healthURL: "http://" + net.JoinHostPort("localhost", mappedPort.Port()) + path,
		username:  username,
		password:  password,
	}
}

func waitForHealthy(
	t *testing.T,
	ctx context.Context,
	service Service,
) {
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
			require.Equal(
				t,
				http.StatusOK,
				status,
			)

			return
		}

		<-ticker.C
	}
}
