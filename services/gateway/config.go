package main

import (
	"fmt"
	"net"
	"net/url"
	"time"
)

const (
	addressEnvironment       = "GATEWAY_ADDR"
	shutdownEnvironment      = "GATEWAY_SHUTDOWN_TIMEOUT"
	upstreamEnvironment      = "GATEWAY_UPSTREAM_TIMEOUT"
	coordinatorEnvironment   = "COORDINATOR_URL"
	captureEnvironment       = "CAPTURE_URL"
	searchEnvironment        = "SEARCH_URL"
	streamTimeoutEnvironment = "GATEWAY_STREAM_TIMEOUT"

	defaultAddress         = ":8080"
	defaultShutdownTimeout = 10 * time.Second
	defaultUpstreamTimeout = 5 * time.Second
	defaultStreamTimeout   = 30 * time.Minute
)

type Config struct {
	address         string
	shutdownTimeout time.Duration
	upstreamTimeout time.Duration
	streamTimeout   time.Duration
	coordinatorURL  *url.URL
	captureURL      *url.URL
	searchURL       *url.URL
}

func LoadConfig(getenv func(string) string) (Config, error) {
	cfg := Config{
		address:         defaultAddress,
		shutdownTimeout: defaultShutdownTimeout,
		upstreamTimeout: defaultUpstreamTimeout,
		streamTimeout:   defaultStreamTimeout,
	}

	if address := getenv(addressEnvironment); address != "" {
		cfg.address = address
	}

	if _, _, err := net.SplitHostPort(cfg.address); err != nil {
		return Config{}, fmt.Errorf("invalid GATEWAY_ADDR: %w", err)
	}

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

	captureRawURL := getenv(captureEnvironment)
	searchRawURL := getenv(searchEnvironment)

	parsedCoordinatorURL, err := getServiceURL(getenv, coordinatorEnvironment)

	if err != nil {
		return Config{}, err
	}

	cfg.coordinatorURL = parsedCoordinatorURL

	if captureRawURL != "" {
		parsedCaptureURL, err := getServiceURL(getenv, captureEnvironment)

		if err != nil {
			return Config{}, err
		}

		cfg.captureURL = parsedCaptureURL
	}

	if searchRawURL != "" {
		parsedSearchURL, err := getServiceURL(getenv, searchEnvironment)

		if err != nil {
			return Config{}, err
		}

		cfg.searchURL = parsedSearchURL
	}

	return cfg, nil
}

func getServiceURL(getenv func(string) string, key string) (*url.URL, error) {
	rawURL := getenv(key)

	if rawURL == "" {
		return nil, nil
	}

	parsedURL, err := url.Parse(rawURL)

	if err != nil {
		return nil, fmt.Errorf(
			"invalid %s: %w",
			key,
			err,
		)
	}

	return parsedURL, nil
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
