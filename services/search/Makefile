.PHONY: install run fmt test test-unit test-integration test-integration-local test-infra-up test-infra-down check

install:
	npm ci


test-infra-up:
	docker compose up -d --wait dynamodb minio opensearch rabbitmq

test-infra-down:
	docker compose down


run:
	npm run build && npm start


fmt:
	npm run format:fix

check:
	npm run format
	npm run lint


test-unit:
	npm test

test-integration:
	ACCESS_KEY_ID=minio \
		SECRET_ACCESS_KEY=minio-secret \
		SEARCH_DYNAMODB_ENDPOINT_URL=http://localhost:8000 \
		SEARCH_S3_ENDPOINT_URL=http://localhost:9000 \
		SEARCH_OPENSEARCH_URL=http://localhost:9200 \
		SEARCH_RABBITMQ_URL=amqp://castellani:castellani@localhost:5672/ \
		npm run test:integration

test-integration-local: test-infra-up test-integration


test: test-unit test-integration
