PYTHON ?= python3

.PHONY: install-dev lint test test-unit test-e2e

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check .

test:
	pytest -m "not e2e"

test-unit:
	pytest -m "not e2e"

test-e2e:
	pytest -m e2e
