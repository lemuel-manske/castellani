package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"
)

const (
	serviceName = "gateway"

	addressFormat = ":%s"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", serviceName)

	if err := run(logger); err != nil {
		logger.Error(
			"gateway stopped",
			"error",
			err,
		)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	cfg, err := LoadConfig(os.Getenv)

	if err != nil {
		return err
	}

	listener, err := net.Listen("tcp", fmt.Sprintf(addressFormat, cfg.port))

	if err != nil {
		return fmt.Errorf(
			"listen on %s: %w",
			cfg.port,
			err,
		)
	}

	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	logger.Info(
		"gateway listening",
		"address",
		listener.Addr().String(),
	)

	server := NewGatewayServer(cfg, logger)

	return server.Serve(ctx, listener)
}
