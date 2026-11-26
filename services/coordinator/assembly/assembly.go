// Package assembly connects Coordinator infrastructure to application use cases.
package assembly

import (
	"context"
	"fmt"

	aws_ "github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awscredentials "github.com/aws/aws-sdk-go-v2/credentials"
	awsdynamo "github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/lemuel-manske/castellani/services/coordinator/adapters/messaging/rabbitmq"
	"github.com/lemuel-manske/castellani/services/coordinator/adapters/persistence/dynamodb"
	"github.com/lemuel-manske/castellani/services/coordinator/application"
)

type CoordinatorContext struct {
	Application *application.Application
	Dispatcher  *application.OutboxDispatcher
	Consumer    *rabbitmq.RabbitConsumer
}

func NewCoordinatorContext(
	ctx context.Context,
	awsRegion string,
	awsAccessKeyID string,
	awsSecretAccessKey string,
	dynamoEndpoint string,
	rabbitURL string,
) (CoordinatorContext, error) {
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
		return CoordinatorContext{}, fmt.Errorf("load persistence configuration: %w", err)
	}

	client := awsdynamo.NewFromConfig(awsConfig, func(options *awsdynamo.Options) {
		if dynamoEndpoint != "" {
			options.BaseEndpoint = aws_.String(dynamoEndpoint)
		}
	})

	repository := dynamodb.NewDynamoArchiveRepository(client)

	outbox := dynamodb.NewDynamoOutboxRepository(client)

	publisher := rabbitmq.NewRabbitPublisher(rabbitURL)

	return CoordinatorContext{
		Application: application.NewApplication(repository),
		Dispatcher:  application.NewOutboxDispatcher(outbox, publisher),
		Consumer: rabbitmq.NewRabbitConsumer(
			rabbitURL,
			publisher,
		),
	}, nil
}
