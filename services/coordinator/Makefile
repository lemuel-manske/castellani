.PHONY: install run fmt check test test-unit test-integration test-infra-up test-infra-down

install:
	go mod download


run:
	go run .


check:
	go vet ./...
	go build ./...

fmt:
	$(MAKE) -C ../../codemods/go apply TARGET=../../services/coordinator


test-infra-up:
	docker compose up -d --wait dynamodb rabbitmq

test-infra-down:
	docker compose down


test-unit:
	go test -v ./...

test-integration:
	COORDINATOR_AWS_REGION=us-east-1 \
		COORDINATOR_AWS_ACCESS_KEY_ID=testing \
		COORDINATOR_AWS_SECRET_ACCESS_KEY=testing \
		COORDINATOR_DYNAMODB_ENDPOINT=http://localhost:8000 \
		COORDINATOR_RABBITMQ_URL=amqp://castellani:castellani@localhost:5672/ \
		COORDINATOR_CONTRACTS_DIR=../../contracts \
		go test -tags=integration -v ./...

test: test-unit test-integration
