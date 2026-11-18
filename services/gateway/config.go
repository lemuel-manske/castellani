package main

import (
	"fmt"
	"net"
	"time"
)

const (
	defaultAddress         = ":8080"
	defaultShutdownTimeout = 10 * time.Second
)

type config struct {
	address         string
	shutdownTimeout time.Duration
}

func loadConfig(getenv func(string) string) (config, error) {
	cfg := config{address: defaultAddress, shutdownTimeout: defaultShutdownTimeout}

	if address := getenv("GATEWAY_ADDR"); address != "" {
		cfg.address = address
	}
	if _, _, err := net.SplitHostPort(cfg.address); err != nil {
		return config{}, fmt.Errorf("invalid GATEWAY_ADDR: %w", err)
	}
	if value := getenv("GATEWAY_SHUTDOWN_TIMEOUT"); value != "" {
		timeout, err := time.ParseDuration(value)
		if err != nil {
			return config{}, fmt.Errorf("invalid GATEWAY_SHUTDOWN_TIMEOUT: %w", err)
		}
		if timeout <= 0 {
			return config{}, fmt.Errorf("GATEWAY_SHUTDOWN_TIMEOUT must be positive")
		}
		cfg.shutdownTimeout = timeout
	}

	return cfg, nil
}
