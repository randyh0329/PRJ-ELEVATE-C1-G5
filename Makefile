.PHONY: setup test run-mocks run-gateway eval clean docker-build

VENV = .venv
PYTHON = $(VENV)/bin/python3
PYTEST = $(VENV)/bin/pytest
UVICORN = $(VENV)/bin/uvicorn

setup:
	@echo "Setting up virtual environment and dependencies..."
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

test:
	@echo "Running all pytest test suites..."
	$(PYTEST) tests/ -v --asyncio-mode=auto

run-mocks:
	@echo "Starting WorkWeek HCM & ServiceImmediately ITSM Mock Backends on port 8080..."
	$(UVICORN) src.mocks.app:mock_app --host 0.0.0.0 --port 8080 --reload

run-gateway:
	@echo "Starting Elevate Ingress API Gateway & Agent Core on port 8000..."
	$(UVICORN) src.gateway.app:gateway_app --host 0.0.0.0 --port 8000 --reload

eval:
	@echo "Running automated evaluation gate on golden dataset and redteam vectors..."
	$(PYTHON) eval/run_all_evals.py

docker-build:
	@echo "Building production container image..."
	docker build -t elevate-agent-solution:1.4.0 .

clean:
	@echo "Cleaning cache files..."
	rm -rf .pytest_cache __pycache__ src/**/__pycache__ tests/__pycache__
