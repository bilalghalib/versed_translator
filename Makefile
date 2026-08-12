.PHONY: test lint fmt

test:
	uv run pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
