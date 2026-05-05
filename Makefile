.DEFAULT_GOAL := help

VENV_PYTHON := .venv/bin/python
VENV_PIP := .venv/bin/pip

.PHONY: help init check-venv check-env run test test-core test-all clean

help:
	@echo "Available targets:"
	@echo "  make init   - Create .venv and install dependencies"
	@echo "  make run    - Start the Matrix todo agent"
	@echo "  make test   - Run core tests"
	@echo "  make test-all   - Run all non-API tests"
	@echo "  make clean  - Remove Python cache files"

init:
	python3 -m venv .venv
	$(VENV_PIP) install -r requirements.txt

check-venv:
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Virtualenv not initialized. Run: make init"; \
		exit 1; \
	fi

check-env:
	@if [ ! -f .env ]; then \
		echo "Missing .env, please copy template first: cp .env.example .env"; \
		exit 1; \
	fi

run: check-venv check-env
	PYTHONPATH=. $(VENV_PYTHON) -m src.main

test: check-venv
	PYTHONPATH=. $(VENV_PYTHON) -m pytest tests/ -m "not api" -v

test-core: check-venv
	PYTHONPATH=. $(VENV_PYTHON) -m pytest tests/ -m "not api" -v

test-all: check-venv
	PYTHONPATH=. $(VENV_PYTHON) -m pytest tests/ -m "not api" -v

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf .pytest_cache 2>/dev/null || true
