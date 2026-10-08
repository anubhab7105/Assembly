.PHONY: test lint run install-dev

install-dev:
	python -m pip install -r requirements.txt -r requirements-dev.txt

test:
	python -m pytest -q

lint:
	python -m ruff check src/providers src/core/keystore.py src/core/config.py src/core/logging_config.py src/api/keys.py src/main.py src/orchestration/orchestrator.py src/orchestration/agent_manager.py src/orchestration/capacity.py tests scripts
	python -m ruff format --check src/providers src/core/keystore.py src/core/config.py src/core/logging_config.py src/api/keys.py src/orchestration/capacity.py tests scripts

run:
	python -m uvicorn src.main:app --reload
