.PHONY: install vendor lint format test cov run-server run-agent demo-services simulate demo docker-up docker-down clean

PYTHON ?= python

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

vendor:
	$(PYTHON) -m scripts.vendor_assets

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

test:
	$(PYTHON) -m pytest tests/

cov:
	$(PYTHON) -m pytest --cov=infraops --cov-report=term-missing tests/

run-server:
	$(PYTHON) -m infraops.server.app

run-agent:
	$(PYTHON) -m infraops.agent.main

demo-services:
	$(PYTHON) -m infraops.demo.demo_service &
	$(PYTHON) -m infraops.demo.demo_upstream &

simulate:
	$(PYTHON) -m scripts.simulate $(or $(NAME),cpu)

demo:
	$(PYTHON) -m scripts.demo_run

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down -v

clean:
	$(PYTHON) -c "import shutil, glob, os; [shutil.rmtree(p, ignore_errors=True) for p in glob.glob('**/__pycache__', recursive=True) + glob.glob('*.egg-info') + ['.pytest_cache', '.ruff_cache', 'htmlcov', '.coverage']]; [os.remove(f) for f in glob.glob('sandbox/run/*.pid') if os.path.exists(f)]"
