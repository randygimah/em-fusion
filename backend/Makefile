.PHONY: lint format type-check test clean install-dev

install-dev:
	uv sync

format:
	black app/ tests/
	ruff check --select I --fix app/ tests/

lint:
	ruff check app/ tests/

type-check:
	mypy app/

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