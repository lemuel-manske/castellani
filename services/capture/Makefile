.PHONY: install run fmt test check

install:
	uv sync --all-groups

run:
	uv run uvicorn capture.main:app --reload --host 0.0.0.0 --port 8000

fmt:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest

check:
	uv run ruff check .
	uv run pyright
