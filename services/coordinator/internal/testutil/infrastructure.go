// Package testutil provides real infrastructure fixtures for Coordinator tests.
package testutil

import (
	"os"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awscredentials "github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/require"

	"github.com/lemuel-manske/castellani/services/coordinator/config"
)

// Infrastructure holds the local dependencies shared by an integration test.
type Infrastructure struct {
	DynamoDB         *dynamodb.Client
	DynamoDBEndpoint string
	RabbitMQ         *amqp.Connection
	RabbitMQURL      string
}

// NewInfrastructure connects to the local services and creates the Coordinator tables.
// Start the Compose services with make test-infra-up before calling it.
func NewInfrastructure(t *testing.T) *Infrastructure {
	t.Helper()

	dynamoDBEndpoint := os.Getenv(config.DynamoDBEndpointEnvironment)
	rabbitMQURL := os.Getenv(config.RabbitMQURLEnvironment)
	awsRegion := os.Getenv(config.RegionEnvironment)
	accessKeyID := os.Getenv(config.AccessKeyIDEnvironment)
	secretAccessKey := os.Getenv(config.SecretAccessKeyEnvironment)

	require.NotEmpty(
		t,
		dynamoDBEndpoint,
		config.DynamoDBEndpointEnvironment,
	)
	require.NotEmpty(
		t,
		rabbitMQURL,
		config.RabbitMQURLEnvironment,
	)
	require.NotEmpty(
		t,
		awsRegion,
		config.RegionEnvironment,
	)
	require.NotEmpty(
		t,
		accessKeyID,
		config.AccessKeyIDEnvironment,
	)
	require.NotEmpty(
		t,
		secretAccessKey,
		config.SecretAccessKeyEnvironment,
	)

	awsConfig, err := awsconfig.LoadDefaultConfig(
		t.Context(),
		awsconfig.WithRegion(awsRegion),
		awsconfig.WithCredentialsProvider(
			awscredentials.NewStaticCredentialsProvider(
				accessKeyID,
				secretAccessKey,
				"",
			),
		),
	)

	require.NoError(t, err)

	dynamoDB := dynamodb.NewFromConfig(awsConfig, func(options *dynamodb.Options) {
		options.BaseEndpoint = aws.String(dynamoDBEndpoint)
	})

	setupDynamoDB(t, dynamoDB)

	rabbitMQ, err := amqp.Dial(rabbitMQURL)
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, rabbitMQ.Close())
	})

	return &Infrastructure{
		DynamoDB:         dynamoDB,
		DynamoDBEndpoint: dynamoDBEndpoint,
		RabbitMQ:         rabbitMQ,
		RabbitMQURL:      rabbitMQURL,
	}
}
