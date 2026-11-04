.PHONY: install lint format typecheck test check run local-tables local-tables-delete places-snapshot

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
	uv run mypy src tests tools

test:
	uv run pytest

check: lint typecheck test

run:
	uv run uvicorn --factory app.main:create_app --reload

# Local DynamoDB table in the developer's AWS account; needs AWS_PROFILE in the environment.
local-tables:
	uv run python -m tools.local_tables create

local-tables-delete:
	uv run python -m tools.local_tables delete

# Rebuild the bundled GeoNames places snapshot (downloads ~14 MB); commit the result.
places-snapshot:
	uv run python -m tools.geonames_snapshot
