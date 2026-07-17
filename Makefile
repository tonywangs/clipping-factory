.PHONY: setup test dashboard run lint

setup:
	uv sync --extra local --extra test

test:
	uv run pytest -q

dashboard:
	uv run uvicorn dashboard.app:app --reload --port 8000

run:
	uv run python -m clipfactory.run --once

lint:
	uv run python -m compileall clipfactory dashboard engine
