.PHONY: setup test dashboard run

setup:
	uv sync --extra local --extra test

test:
	uv run pytest

dashboard:
	uv run uvicorn dashboard.app:app --reload --port 8000

run:
	uv run python -m clipfactory.run --once
