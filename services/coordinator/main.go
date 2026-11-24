package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"

	"github.com/lemuel-manske/castellani/services/coordinator/assembly"
)

const (
	serviceName = "coordinator"

	addressFormat = ":%s"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", serviceName)

	if err := run(logger); err != nil {
		logger.Error(
			"coordinator stopped",
			"error",
			err,
		)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	config, err := LoadConfig(os.Getenv)

	if err != nil {
		return err
	}

	listener, err := net.Listen("tcp", fmt.Sprintf(addressFormat, config.port))

	if err != nil {
		return fmt.Errorf(
			"listen on %s: %w",
			config.port,
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
		"coordinator listening",
		"address",
		listener.Addr().String(),
	)

	built, err := assembly.NewComponents(
		ctx,
		config.region,
		config.awsAccessKeyID,
		config.awsSecretAccessKey,
		config.dynamoEndpoint,
		config.rabbitURL,
	)

	if err != nil {
		return err
	}

	StartWorkers(
		ctx,
		logger,
		built.Dispatcher,
		built.Consumer,
		built.Application,
		config.reconcileInterval,
		config.stalledWorkflowAge,
	)

	server := NewCoordinatorServer(
		config,
		built.Application,
		logger,
	)

	return server.Serve(ctx, listener)
}
