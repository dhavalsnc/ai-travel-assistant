PY := .venv/Scripts/python
PIP := .venv/Scripts/pip
STREAMLIT := .venv/Scripts/streamlit
RUFF := .venv/Scripts/ruff

.PHONY: setup ingest run test lint

setup:
	python -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@echo Done. Copy .env.example to .env and add your GOOGLE_API_KEY.

ingest:
	$(PY) -m travel_assistant.ingestion.build_index

run:
	$(STREAMLIT) run src/travel_assistant/ui/app.py

test:
	$(PY) -m pytest -v

lint:
	$(RUFF) check src tests
