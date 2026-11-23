package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/lemuel-manske/castellani/services/coordinator/assembly"
	persistence "github.com/lemuel-manske/castellani/services/coordinator/persistence/dynamodb"
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

	awsConfig, err := awsconfig.LoadDefaultConfig(
		ctx,
		awsconfig.WithRegion(config.region),
		awsconfig.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(
				config.awsAccessKeyID,
				config.awsSecretAccessKey,
				"",
			),
		),
	)

	if err != nil {
		return fmt.Errorf("load persistence configuration: %w", err)
	}

	client := dynamodb.NewFromConfig(awsConfig, func(options *dynamodb.Options) {
		if config.dynamoEndpoint != "" {
			options.BaseEndpoint = aws.String(config.dynamoEndpoint)
		}
	})

	repository := persistence.NewDynamoRepository(client)

	built := assembly.NewComponents(
		repository,
		config.rabbitURL,
	)

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
