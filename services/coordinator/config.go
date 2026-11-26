package main

import (
	"fmt"
	"time"

	env "github.com/lemuel-manske/castellani/services/coordinator/config"
)

const (
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

	config.port = getenv(env.PortEnvironment)

	var err error

	config.shutdownTimeout, err = getDurationSetting(
		getenv,
		env.ShutdownEnvironment,
		config.shutdownTimeout,
	)

	if err != nil {
		return Config{}, err
	}

	config.reconcileInterval, err = getDurationSetting(
		getenv,
		env.ReconcileIntervalEnvironment,
		config.reconcileInterval,
	)

	if err != nil {
		return Config{}, err
	}

	config.stalledWorkflowAge, err = getDurationSetting(
		getenv,
		env.StalledWorkflowAgeEnvironment,
		config.stalledWorkflowAge,
	)

	if err != nil {
		return Config{}, err
	}

	config.region = getenv(env.RegionEnvironment)
	config.awsAccessKeyID = getenv(env.AccessKeyIDEnvironment)
	config.awsSecretAccessKey = getenv(env.SecretAccessKeyEnvironment)

	if config.awsAccessKeyID == "" {
		return Config{}, fmt.Errorf("%s is required", env.AccessKeyIDEnvironment)
	}

	if config.awsSecretAccessKey == "" {
		return Config{}, fmt.Errorf("%s is required", env.SecretAccessKeyEnvironment)
	}

	config.dynamoEndpoint = getenv(env.DynamoDBEndpointEnvironment)
	config.rabbitURL = getenv(env.RabbitMQURLEnvironment)

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
