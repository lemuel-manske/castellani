// Package assembly connects Coordinator infrastructure to application use cases.
package assembly

import (
	"context"
	"fmt"

	aws_ "github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awscredentials "github.com/aws/aws-sdk-go-v2/credentials"
	awsdynamo "github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/lemuel-manske/castellani/services/coordinator/adapters/messaging/dispatcher"
	"github.com/lemuel-manske/castellani/services/coordinator/adapters/messaging/rabbitmq"
	"github.com/lemuel-manske/castellani/services/coordinator/adapters/persistence/dynamodb"
	"github.com/lemuel-manske/castellani/services/coordinator/application"
)

type Components struct {
	Application *application.Application
	Dispatcher  *dispatcher.Dispatcher
	Consumer    *rabbitmq.RabbitConsumer
}

func NewComponents(
	ctx context.Context,
	awsRegion string,
	awsAccessKeyID string,
	awsSecretAccessKey string,
	dynamoEndpoint string,
	rabbitURL string,
) (Components, error) {
	awsConfig, err := awsconfig.LoadDefaultConfig(
		ctx,
		awsconfig.WithRegion(awsRegion),
		awsconfig.WithCredentialsProvider(
			awscredentials.NewStaticCredentialsProvider(
				awsAccessKeyID,
				awsSecretAccessKey,
				"",
			),
		),
	)

	if err != nil {
		return Components{}, fmt.Errorf("load persistence configuration: %w", err)
	}

	client := awsdynamo.NewFromConfig(awsConfig, func(options *awsdynamo.Options) {
		if dynamoEndpoint != "" {
			options.BaseEndpoint = aws_.String(dynamoEndpoint)
		}
	})

	repository := dynamodb.NewDynamoArchiveRepository(client)

	outbox := dynamodb.NewDynamoOutbox(client)

	publisher := rabbitmq.NewRabbitPublisher(rabbitURL)

	return Components{
		Application: application.NewApplication(repository),
		Dispatcher:  dispatcher.NewDispatcher(outbox, publisher),
		Consumer: rabbitmq.NewRabbitConsumer(
			rabbitURL,
			publisher,
		),
	}, nil
}
