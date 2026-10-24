.PHONY: install lint format typecheck test check run

install:
	uv sync --locked
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy src tests

test:
	uv run pytest

check: lint typecheck test

run:
	uv run uvicorn --factory app.main:create_app --reload
