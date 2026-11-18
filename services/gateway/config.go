package main

import (
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

const (
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

	if address := getenv("GATEWAY_ADDR"); address != "" {
		cfg.address = address
	}
	if _, _, err := net.SplitHostPort(cfg.address); err != nil {
		return config{}, fmt.Errorf("invalid GATEWAY_ADDR: %w", err)
	}

	var err error
	if cfg.shutdownTimeout, err = durationSetting(getenv, "GATEWAY_SHUTDOWN_TIMEOUT", cfg.shutdownTimeout); err != nil {
		return config{}, err
	}
	if cfg.upstreamTimeout, err = durationSetting(getenv, "GATEWAY_UPSTREAM_TIMEOUT", cfg.upstreamTimeout); err != nil {
		return config{}, err
	}

	rawURL := getenv("COORDINATOR_URL")
	if rawURL == "" {
		return config{}, fmt.Errorf("COORDINATOR_URL is required")
	}
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return config{}, fmt.Errorf("invalid COORDINATOR_URL: %w", err)
	}
	if (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" ||
		parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" ||
		(parsed.Path != "" && parsed.Path != "/") || strings.HasSuffix(parsed.Host, "@") {
		return config{}, fmt.Errorf("COORDINATOR_URL must be an absolute HTTP(S) origin without credentials, path, query or fragment")
	}
	cfg.coordinatorURL = parsed
	return cfg, nil
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
