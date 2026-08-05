.PHONY: sync test run image

sync:
	uv sync --all-extras --frozen

test:
	uv run pytest -q

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8091

image:
	docker build --tag tasklattice-model-guardrails:dev .
