module github.com/lemuel-manske/castellani/services/coordinator

go 1.25.0

toolchain go1.25.4

require (
	github.com/aws/aws-sdk-go-v2 v1.48.0
	github.com/aws/aws-sdk-go-v2/config v1.33.17
	github.com/aws/aws-sdk-go-v2/service/dynamodb v1.74.0
	github.com/go-chi/chi/v5 v5.2.3
	github.com/lemuel-manske/castellani/libs/httpx v0.0.0
	github.com/rabbitmq/amqp091-go v1.10.0
)

require (
	github.com/aws/aws-sdk-go-v2/credentials v1.20.17 // indirect
	github.com/aws/aws-sdk-go-v2/feature/ec2/imds v1.20.8 // indirect
	github.com/aws/aws-sdk-go-v2/internal/configsources v1.5.12 // indirect
	github.com/aws/aws-sdk-go-v2/internal/endpoints/v2 v2.8.12 // indirect
	github.com/aws/aws-sdk-go-v2/internal/v4a v1.5.11 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/accept-encoding v1.13.25 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/endpoint-discovery v1.13.12 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/presigned-url v1.14.11 // indirect
	github.com/aws/aws-sdk-go-v2/service/signin v1.13.0 // indirect
	github.com/aws/aws-sdk-go-v2/service/sso v1.39.4 // indirect
	github.com/aws/aws-sdk-go-v2/service/ssooidc v1.44.4 // indirect
	github.com/aws/aws-sdk-go-v2/service/sts v1.51.9 // indirect
	github.com/aws/smithy-go v1.28.9 // indirect
)

replace github.com/lemuel-manske/castellani/libs/httpx => ../../libs/httpx
