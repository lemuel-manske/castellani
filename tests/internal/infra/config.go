package infra

import (
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

const (
	rabbitMQUsername = "castellani"
	rabbitMQPassword = "castellani"

	terraformLockFile = ".terraform.lock.hcl"
)

func repositoryRoot(t *testing.T) string {
	t.Helper()

	_, file, _, ok := runtime.Caller(0)
	require.True(t, ok, "locate repository root")

	return filepath.Join(filepath.Dir(file), "..", "..", "..")
}

func prepareTerraform(t *testing.T, root string) string {
	t.Helper()

	source := filepath.Join(root, "infra", "terraform")
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

		require.NoError(t, os.WriteFile(filepath.Join(target, name), contents, 0o600))
	}

	return target
}

func stackEnvironment(terraformDir string) map[string]string {
	return map[string]string{
		"AWS_REGION": "us-east-1",

		"AWS_ACCESS_KEY_ID":     "test",
		"AWS_SECRET_ACCESS_KEY": "test",

		"RABBITMQ_USERNAME": rabbitMQUsername,
		"RABBITMQ_USER":     rabbitMQUsername,
		"RABBITMQ_PASSWORD": rabbitMQPassword,

		"COORDINATOR_URL":          "http://coordinator:8081",
		"CAPTURE_URL":              "http://capture:8000",
		"CAPTURE_LOGIN_URL":        "http://capture-login:8010",
		"SEARCH_URL":               "http://search:8082",
		"CAPTURE_AUTH_PROFILE_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",

		"TERRAFORM_DIR": terraformDir,
		"TERRAFORM_UID": strconv.Itoa(os.Getuid()),
		"TERRAFORM_GID": strconv.Itoa(os.Getgid()),

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
