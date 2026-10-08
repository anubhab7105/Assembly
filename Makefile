.PHONY: test lint run install-dev

install-dev:
	python -m pip install -r requirements.txt -r requirements-dev.txt

test:
	python -m pytest -q

lint:
	python -m ruff check src tests
	python -m ruff format --check src/providers/mock_provider.py tests

run:
	python -m uvicorn src.main:app --reload
