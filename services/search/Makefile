.PHONY: install run fmt test test-unit test-integration test-infra-up test-infra-down check

install:
	npm ci


test-infra-up:
	docker compose up -d --wait dynamodb-local opensearch rabbitmq
	docker compose up -d localstack
	timeout 120 sh -c 'until curl -fsS http://localhost:4566/_localstack/health >/dev/null; do sleep 2; done' || { docker compose logs localstack; exit 1; }
		sleep 2; \
	done

test-infra-down:
	docker compose down


run:
	npm run build && npm start


fmt:
	npm run format:fix

check:
	npm run format
	npm run lint
	npm run typecheck


test-unit:
	npm test

test-integration:
	SEARCH_DYNAMODB_ENDPOINT_URL=http://localhost:8000 \
		SEARCH_S3_ENDPOINT_URL=http://localhost:4566 \
		SEARCH_OPENSEARCH_URL=http://localhost:9200 \
		SEARCH_RABBITMQ_URL=amqp://castellani:castellani@localhost:5672/ \
		npm run test:integration

test: test-unit test-integration
