package main

import (
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

const (
	addressEnvironment = "GATEWAY_ADDR"
	shutdownEnvironment = "GATEWAY_SHUTDOWN_TIMEOUT"
	upstreamEnvironment = "GATEWAY_UPSTREAM_TIMEOUT"
	coordinatorEnvironment = "COORDINATOR_URL"

	defaultAddress         = ":8080"
	defaultShutdownTimeout = 10 * time.Second
	defaultUpstreamTimeout = 5 * time.Second
)

type config struct {
	address         string
	shutdownTimeout time.Duration
	upstreamTimeout time.Duration
	coordinatorURL  *url.URL
}

func loadConfig(getenv func(string) string) (config, error) {
	cfg := config{
		address:         defaultAddress,
		shutdownTimeout: defaultShutdownTimeout,
		upstreamTimeout: defaultUpstreamTimeout,
	}

	if address := getenv(addressEnvironment); address != "" {
		cfg.address = address
	}

	if _, _, err := net.SplitHostPort(cfg.address); err != nil {
		return config{}, fmt.Errorf("invalid GATEWAY_ADDR: %w", err)
	}

	var err error

	if cfg.shutdownTimeout, err = durationSetting(getenv, shutdownEnvironment, cfg.shutdownTimeout); err != nil {
		return config{}, err
	}

	if cfg.upstreamTimeout, err = durationSetting(getenv, upstreamEnvironment, cfg.upstreamTimeout); err != nil {
		return config{}, err
	}

	rawURL := getenv(coordinatorEnvironment)

	if rawURL == "" {
		return config{}, fmt.Errorf("COORDINATOR_URL is required")
	}
	parsed, err := url.Parse(rawURL)

	if err != nil {
		return config{}, fmt.Errorf("invalid COORDINATOR_URL: %w", err)
	}

	if !validCoordinatorOrigin(parsed) {
		return config{}, fmt.Errorf("COORDINATOR_URL must be an absolute HTTP(S) origin without credentials, path, query or fragment")
	}
	cfg.coordinatorURL = parsed
	return cfg, nil
}

func validCoordinatorOrigin(parsed *url.URL) bool {
	httpScheme := parsed.Scheme == "http" || parsed.Scheme == "https"
	validAuthority := parsed.Host != "" && parsed.User == nil
	cleanPath := parsed.Path == "" || parsed.Path == "/"
	noAdditionalParts := parsed.RawQuery == "" && parsed.Fragment == ""

	return httpScheme && validAuthority && cleanPath && noAdditionalParts && !strings.HasSuffix(parsed.Host, "@")
}

func durationSetting(getenv func(string) string, key string, fallback time.Duration) (time.Duration, error) {
	value := getenv(key)

	if value == "" {
		return fallback, nil
	}
	duration, err := time.ParseDuration(value)

	if err != nil {
		return 0, fmt.Errorf("invalid %s: %w", key, err)
	}

	if duration <= 0 {
		return 0, fmt.Errorf("%s must be positive", key)
	}
	return duration, nil
}
