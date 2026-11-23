package main

import (
	"fmt"
	"time"
)

const (
	portEnvironment = "GATEWAY_PORT"

	coordinatorEnvironment = "GATEWAY_COORDINATOR_URL"
	captureEnvironment     = "GATEWAY_CAPTURE_URL"
	searchEnvironment      = "GATEWAY_SEARCH_URL"

	shutdownEnvironment      = "GATEWAY_SHUTDOWN_TIMEOUT"
	upstreamEnvironment      = "GATEWAY_UPSTREAM_TIMEOUT"
	streamTimeoutEnvironment = "GATEWAY_STREAM_TIMEOUT"

	defaultShutdownTimeout = 10 * time.Second
	defaultUpstreamTimeout = 5 * time.Second
	defaultStreamTimeout   = 30 * time.Minute
)

type Config struct {
	port            string
	shutdownTimeout time.Duration
	upstreamTimeout time.Duration
	streamTimeout   time.Duration
	coordinatorURL  string
	captureURL      string
	searchURL       string
}

func LoadConfig(getenv func(string) string) (Config, error) {
	cfg := Config{
		shutdownTimeout: defaultShutdownTimeout,
		upstreamTimeout: defaultUpstreamTimeout,
		streamTimeout:   defaultStreamTimeout,
	}

	cfg.port = getenv(portEnvironment)

	var err error

	cfg.shutdownTimeout, err = getDurationSetting(
		getenv,
		shutdownEnvironment,
		cfg.shutdownTimeout,
	)

	if err != nil {
		return Config{}, err
	}

	cfg.upstreamTimeout, err = getDurationSetting(
		getenv,
		upstreamEnvironment,
		cfg.upstreamTimeout,
	)

	if err != nil {
		return Config{}, err
	}

	cfg.streamTimeout, err = getDurationSetting(
		getenv,
		streamTimeoutEnvironment,
		cfg.streamTimeout,
	)

	if err != nil {
		return Config{}, err
	}

	cfg.coordinatorURL = getenv(coordinatorEnvironment)
	cfg.captureURL = getenv(captureEnvironment)
	cfg.searchURL = getenv(searchEnvironment)

	return cfg, nil
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
