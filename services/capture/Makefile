.PHONY: install run fmt test check

install:
	uv sync --all-groups

fmt:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest

check:
	uv run ruff check .
	uv run pyright


run:
	PYTHONPATH=src uv run uvicorn capture.main:app --reload --host 0.0.0.0 --port 8000
