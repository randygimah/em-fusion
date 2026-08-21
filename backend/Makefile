# Native command surface for the backend. Every target runs through `uv run`,
# so none of them needs .venv activated first and all of them use the versions
# pinned in uv.lock. The root Makefile is the containerised equivalent.

.PHONY: help install-dev format lint type-check test check clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install-dev: ## Install dependencies from uv.lock
	uv sync

format: ## Black, then ruff's import sorting (writes)
	uv run black app/ tests/
	uv run ruff check --select I --fix app/ tests/

lint: ## ruff check
	uv run ruff check app/ tests/

type-check: ## mypy over app/
	uv run mypy app/

test: ## pytest with coverage, gated at the 90% the workflow requires
	uv run pytest --tb=short --cov=app --cov-report=term-missing --cov-fail-under=90

check: format lint type-check test ## Everything, in that order

clean: ## Remove bytecode and build leftovers
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
