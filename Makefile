PYTHON ?= .venv/bin/python
PIP := $(PYTHON) -m pip

.PHONY: setup train export-model migrate import-content run test lint clean

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-dev.txt

train:
	$(PYTHON) run_all.py

export-model:
	$(PYTHON) scripts/export_serving_model.py

migrate:
	.venv/bin/alembic upgrade head

import-content:
	$(PYTHON) -m app.content import-all

run:
	$(PYTHON) run_server.py

test:
	$(PYTHON) -m pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/mypy

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find app src tests migrations scripts -type d -name __pycache__ -prune -exec rm -rf {} +
