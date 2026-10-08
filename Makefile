.PHONY: test lint run install-dev

install-dev:
	python -m pip install -r requirements.txt -r requirements-dev.txt

test:
	python -m pytest -q

lint:
	python -m ruff check src/providers src/core/keystore.py src/core/config.py src/api/keys.py tests scripts
	python -m ruff format --check src/providers src/core/keystore.py src/core/config.py src/api/keys.py tests scripts

run:
	python -m uvicorn src.main:app --reload
