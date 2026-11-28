package infra

import (
	"fmt"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

const (
	e2eProjectName = "castellani-e2e"

	captureWorkerReplicaCount = 3

	rabbitMQUsername = "castellani"
	rabbitMQPassword = "castellani"

	awsRegion          = "us-east-1"
	awsAccessKeyID     = "test"
	awsSecretAccessKey = "test"

	terraformLockFile = ".terraform.lock.hcl"
)

func repositoryRoot() (string, error) {
	_, file, _, ok := runtime.Caller(0)

	if !ok {
		return "", fmt.Errorf("locate repository root")
	}

	return filepath.Join(filepath.Dir(file), "../../.."), nil
}

func prepareTerraform(root string) (string, error) {
	target, err := terraformTarget()

	if err != nil {
		return "", err
	}

	source := filepath.Join(
		root,
		"infra",
		"terraform",
	)

	entries, err := os.ReadDir(source)

	if err != nil {
		return "", fmt.Errorf("read terraform sources: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		name := entry.Name()

		if !strings.HasSuffix(name, ".tf") && name != terraformLockFile {
			continue
		}

		contents, err := os.ReadFile(filepath.Join(source, name))

		if err != nil {
			return "", fmt.Errorf(
				"read terraform file %s: %w",
				name,
				err,
			)
		}

		if err := os.WriteFile(
			filepath.Join(target, name),
			contents,
			0o600,
		); err != nil {
			return "", fmt.Errorf(
				"write terraform file %s: %w",
				name,
				err,
			)
		}
	}

	return target, nil
}

func terraformTarget() (string, error) {
	return os.MkdirTemp("", "castellani-e2e-terraform-")
}

func stackEnvironment(terraformDir string) (map[string]string, error) {
	env := map[string]string{
		"AWS_REGION":               awsRegion,
		"AWS_ACCESS_KEY_ID":        awsAccessKeyID,
		"AWS_SECRET_ACCESS_KEY":    awsSecretAccessKey,
		"RABBITMQ_USERNAME":        rabbitMQUsername,
		"RABBITMQ_USER":            rabbitMQUsername,
		"RABBITMQ_PASSWORD":        rabbitMQPassword,
		"COORDINATOR_URL":          "http://coordinator:8081",
		"CAPTURE_URL":              "http://capture-worker:8000",
		"CAPTURE_LOGIN_URL":        "http://capture-login:8010",
		"SEARCH_URL":               "http://search:8082",
		"CAPTURE_AUTH_PROFILE_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
		"TERRAFORM_DIR":            terraformDir,
		"TERRAFORM_UID":            strconv.Itoa(os.Getuid()),
		"TERRAFORM_GID":            strconv.Itoa(os.Getgid()),
		"CAPTURE_PORT":             "0",
	}

	portNames := []string{
		"MINISTACK_PORT",
		"RABBITMQ_PORT",
		"RABBITMQ_MANAGEMENT_PORT",
		"OPENSEARCH_PORT",
		"COORDINATOR_PORT",
		"GATEWAY_PORT",
		"SEARCH_PORT",
	}

	listeners := make(
		[]net.Listener,
		0,
		len(portNames),
	)
	defer func() {
		for _, listener := range listeners {
			listener.Close()
		}
	}()

	for _, name := range portNames {
		listener, err := net.Listen("tcp", "127.0.0.1:0")

		if err != nil {
			return nil, fmt.Errorf(
				"reserve %s: %w",
				name,
				err,
			)
		}

		listeners = append(listeners, listener)

		_, port, err := net.SplitHostPort(listener.Addr().String())

		if err != nil {
			return nil, fmt.Errorf(
				"resolve %s: %w",
				name,
				err,
			)
		}

		env[name] = port
	}

	return env, nil
}
