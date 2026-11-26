package config

const (
	PortEnvironment               = "COORDINATOR_PORT"
	RegionEnvironment             = "COORDINATOR_AWS_REGION"
	AccessKeyIDEnvironment        = "COORDINATOR_AWS_ACCESS_KEY_ID"
	SecretAccessKeyEnvironment    = "COORDINATOR_AWS_SECRET_ACCESS_KEY"
	ShutdownEnvironment           = "COORDINATOR_SHUTDOWN_TIMEOUT"
	ReconcileIntervalEnvironment  = "COORDINATOR_RECONCILIATION_INTERVAL"
	StalledWorkflowAgeEnvironment = "COORDINATOR_STALLED_WORKFLOW_AGE"
	DynamoDBEndpointEnvironment   = "COORDINATOR_DYNAMODB_ENDPOINT"
	RabbitMQURLEnvironment        = "COORDINATOR_RABBITMQ_URL"
)
