.PHONY: install run-worker run-login fmt test test-unit test-integration check test-infra-up test-infra-down

install:
	uv sync --all-groups


test-infra-up:
	docker compose up -d --wait dynamodb minio rabbitmq

test-infra-down:
	docker compose down


test-unit:
	CAPTURE_CONTRACTS_DIR=../../contracts \
		uv run pytest -m "not integration"

test-integration:
	CAPTURE_DYNAMODB_ENDPOINT_URL=http://localhost:8000 \
		CAPTURE_S3_ENDPOINT_URL=http://localhost:9000 \
		CAPTURE_AWS_ACCESS_KEY_ID=minio \
		CAPTURE_AWS_SECRET_ACCESS_KEY=minio-secret \
		CAPTURE_RABBITMQ_URL=amqp://castellani:castellani@localhost:5672/ \
		CAPTURE_CONTRACTS_DIR=../../contracts \
		uv run pytest -m integration

test: test-unit test-integration


fmt:
	uv run ruff format .
	uv run ruff check --fix .

check:
	uv run ruff check .
	uv run pyright


run-worker:
	PYTHONPATH=src uv run uvicorn capture.api:app --factory --host 0.0.0.0 --port 8000


run-login:
	PYTHONPATH=src uv run uvicorn login.api:app --factory --host 0.0.0.0 --port 8010
