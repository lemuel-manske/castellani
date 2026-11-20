.PHONY: install run fmt test test-unit test-integration check

install:
	uv sync --all-groups

fmt:
	uv run ruff format .
	uv run ruff check --fix .

test-unit:
	uv run pytest -m "not integration"

test-integration:
	uv run pytest -m integration

test: test-unit test-integration

check:
	uv run ruff check .
	uv run pyright


run:
	PYTHONPATH=src uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
