package main

import (
	"fmt"
	"net"
	"time"
)

const (
	addressEnvironment            = "COORDINATOR_ADDR"
	shutdownEnvironment           = "COORDINATOR_SHUTDOWN_TIMEOUT"
	regionEnvironment             = "COORDINATOR_AWS_REGION"
	endpointEnvironment           = "COORDINATOR_DYNAMODB_ENDPOINT"
	archivesEnvironment           = "COORDINATOR_ARCHIVES_TABLE"
	submissionsEnvironment        = "COORDINATOR_SUBMISSIONS_TABLE"
	outboxEnvironment             = "COORDINATOR_OUTBOX_TABLE"
	inboxEnvironment              = "COORDINATOR_INBOX_TABLE"
	rabbitURLEnvironment          = "COORDINATOR_RABBITMQ_URL"
	rabbitExchangeEnvironment     = "COORDINATOR_RABBITMQ_EXCHANGE"
	reconcileIntervalEnvironment  = "COORDINATOR_RECONCILIATION_INTERVAL"
	stalledWorkflowAgeEnvironment = "COORDINATOR_STALLED_WORKFLOW_AGE"

	defaultAddress            = ":8081"
	defaultShutdownTimeout    = 10 * time.Second
	defaultRegion             = "us-east-1"
	defaultArchivesTable      = "coordinator_archive_runs"
	defaultSubmissionsTable   = "coordinator_submission_keys"
	defaultOutboxTable        = "coordinator_outbox"
	defaultInboxTable         = "coordinator_inbox"
	defaultRabbitURL          = "amqp://guest:guest@localhost:5672/"
	defaultRabbitExchange     = "castellani.events"
	defaultReconcileInterval  = 30 * time.Second
	defaultStalledWorkflowAge = 2 * time.Minute
)

type Config struct {
	address            string
	shutdownTimeout    time.Duration
	region             string
	endpoint           string
	archivesTable      string
	submissionsTable   string
	outboxTable        string
	inboxTable         string
	rabbitURL          string
	rabbitExchange     string
	reconcileInterval  time.Duration
	stalledWorkflowAge time.Duration
}

func LoadConfig(getenv func(string) string) (Config, error) {
	config := Config{
		address:            defaultAddress,
		shutdownTimeout:    defaultShutdownTimeout,
		region:             defaultRegion,
		archivesTable:      defaultArchivesTable,
		submissionsTable:   defaultSubmissionsTable,
		outboxTable:        defaultOutboxTable,
		inboxTable:         defaultInboxTable,
		rabbitURL:          defaultRabbitURL,
		rabbitExchange:     defaultRabbitExchange,
		reconcileInterval:  defaultReconcileInterval,
		stalledWorkflowAge: defaultStalledWorkflowAge,
	}

	if address := getenv(addressEnvironment); address != "" {
		config.address = address
	}

	if _, _, err := net.SplitHostPort(config.address); err != nil {
		return Config{}, fmt.Errorf(
			"invalid %s: %w",
			addressEnvironment,
			err,
		)
	}

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

	if region := getenv(regionEnvironment); region != "" {
		config.region = region
	}

	config.endpoint = getenv(endpointEnvironment)

	if name := getenv(archivesEnvironment); name != "" {
		config.archivesTable = name
	}

	if name := getenv(submissionsEnvironment); name != "" {
		config.submissionsTable = name
	}

	if name := getenv(outboxEnvironment); name != "" {
		config.outboxTable = name
	}

	if name := getenv(inboxEnvironment); name != "" {
		config.inboxTable = name
	}

	if value := getenv(rabbitURLEnvironment); value != "" {
		config.rabbitURL = value
	}

	if value := getenv(rabbitExchangeEnvironment); value != "" {
		config.rabbitExchange = value
	}

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
