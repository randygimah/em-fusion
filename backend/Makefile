.PHONY: lint format type-check test clean install-dev

install-dev:
	pip install -r requirements.txt

format:
	black backend/
	isort backend/

lint:
	flake8 backend/
	isort --check-only --diff backend/

type-check:
	mypy backend/

test:
	pytest --tb=short

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +

# Run all checks
check: format lint type-check test

# Setup development environment
setup: install-dev
	pre-commit install  # if pre-commit is added later