.PHONY: install fmt test test-unit test-integration check

install:
	uv sync --all-groups


test-unit:
	uv run pytest -m "not integration"


test-integration:
	uv run pytest -m integration


test: test-unit test-integration


fmt:
	uv run ruff format .
	uv run ruff check --fix .


check:
	uv run ruff check .
	uv run pyright
