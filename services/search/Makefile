.PHONY: install run fmt test test-unit test-integration test-infra-up test-infra-down check

install:
	npm ci

test-infra-up:
	docker compose up -d --wait dynamodb-local minio opensearch rabbitmq

test-infra-down:
	docker compose down

run:
	npm run build && npm start

fmt:
	npm run format

check:
	npm run format:check
	npm run typecheck
	npm run lint

test-unit:
	npm test

test-integration:
	SEARCH_DYNAMODB_ENDPOINT_URL=http://localhost:8000 \
		SEARCH_S3_ENDPOINT_URL=http://localhost:9000 \
		SEARCH_OPENSEARCH_URL=http://localhost:9200 \
		SEARCH_RABBITMQ_URL=amqp://castellani:castellani@localhost:5672/ \
		npm run test:integration

test: test-unit test-integration
