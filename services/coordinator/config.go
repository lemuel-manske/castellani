package main

import (
	"fmt"
	"time"
)

const (
	portEnvironment = "COORDINATOR_PORT"

	regionEnvironment = "COORDINATOR_AWS_REGION"

	accessKeyIDEnvironment     = "COORDINATOR_AWS_ACCESS_KEY_ID"
	secretAccessKeyEnvironment = "COORDINATOR_AWS_SECRET_ACCESS_KEY"

	shutdownEnvironment           = "COORDINATOR_SHUTDOWN_TIMEOUT"
	reconcileIntervalEnvironment  = "COORDINATOR_RECONCILIATION_INTERVAL"
	stalledWorkflowAgeEnvironment = "COORDINATOR_STALLED_WORKFLOW_AGE"

	dynamoEndpointEnvironment = "COORDINATOR_DYNAMODB_ENDPOINT"

	rabbitURLEnvironment = "COORDINATOR_RABBITMQ_URL"

	defaultShutdownTimeout    = 10 * time.Second
	defaultReconcileInterval  = 30 * time.Second
	defaultStalledWorkflowAge = 2 * time.Minute
)

type Config struct {
	port               string
	region             string
	awsAccessKeyID     string
	awsSecretAccessKey string
	shutdownTimeout    time.Duration
	reconcileInterval  time.Duration
	stalledWorkflowAge time.Duration
	dynamoEndpoint     string
	rabbitURL          string
}

func LoadConfig(getenv func(string) string) (Config, error) {
	config := Config{
		shutdownTimeout:    defaultShutdownTimeout,
		reconcileInterval:  defaultReconcileInterval,
		stalledWorkflowAge: defaultStalledWorkflowAge,
	}

	config.port = getenv(portEnvironment)

	var err error

	config.shutdownTimeout, err = getDurationSetting(
		getenv,
		shutdownEnvironment,
		config.shutdownTimeout,
	)

	if err != nil {
		return Config{}, err
	}

	config.reconcileInterval, err = getDurationSetting(
		getenv,
		reconcileIntervalEnvironment,
		config.reconcileInterval,
	)

	if err != nil {
		return Config{}, err
	}

	config.stalledWorkflowAge, err = getDurationSetting(
		getenv,
		stalledWorkflowAgeEnvironment,
		config.stalledWorkflowAge,
	)

	if err != nil {
		return Config{}, err
	}

	config.region = getenv(regionEnvironment)
	config.awsAccessKeyID = getenv(accessKeyIDEnvironment)
	config.awsSecretAccessKey = getenv(secretAccessKeyEnvironment)

	if config.awsAccessKeyID == "" {
		return Config{}, fmt.Errorf("%s is required", accessKeyIDEnvironment)
	}

	if config.awsSecretAccessKey == "" {
		return Config{}, fmt.Errorf("%s is required", secretAccessKeyEnvironment)
	}

	config.dynamoEndpoint = getenv(dynamoEndpointEnvironment)
	config.rabbitURL = getenv(rabbitURLEnvironment)

	return config, nil
}

func getDurationSetting(
	getenv func(string) string,
	key string,
	fallback time.Duration,
) (time.Duration, error) {
	value := getenv(key)

	if value == "" {
		return fallback, nil
	}

	duration, err := time.ParseDuration(value)

	if err != nil {
		return 0, fmt.Errorf(
			"invalid %s: %w",
			key,
			err,
		)
	}

	if duration <= 0 {
		return 0, fmt.Errorf("%s must be positive", key)
	}

	return duration, nil
}
