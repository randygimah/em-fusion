# EM Fusion — single command surface over compose.yaml.
# Backend-only tooling (black/ruff/mypy against a local venv) stays in
# backend/Makefile; everything here goes through Docker.

.DEFAULT_GOAL := help
.PHONY: help build build-backend build-frontend-test up demo down restart \
        logs ps shell db-shell db-reset generate ensure-artifacts \
        test test-backend test-frontend lint format type-check check smoke clean

COMPOSE ?= docker compose
DATA_DIR ?= data

# Kept deliberately in step with backend/Makefile's `test` target. The two run
# the same suite in different environments, and a coverage gate that applies in
# one but not the other means `make check` means two different things depending
# on where it was typed. CI (ops-002) calling one of them is what will stop this
# drifting again.
PYTEST_ARGS ?= --tb=short --cov=app --cov-report=term-missing --cov-fail-under=90

# Artefacts the pipeline generates and `demo` needs on disk before it starts.
# Deliberately empty for now. The OpenSky extract is not generated here and is
# not committed either -- the licence forbids redistributing it (DLA §3(iii)),
# so it is rebuilt from the committed manifest by `python -m app.corpus.build`
# (adp-006), which is a licence-accepting operator action rather than something
# a build target may run unattended. Synthetic observations are regenerated
# byte-identically from a seed rather than stored (scn-001). Add paths here as
# the pipeline starts producing files; `ensure-artifacts` guards them
# automatically.
ARTIFACTS :=

help: ## Show this help
	@echo "EM Fusion — make targets:"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## ---------------------------------------------------------------- stack

build: ## Build every image, pipeline and test profiles included
	$(COMPOSE) --profile pipeline --profile test build

build-backend: ## Refresh the backend dev image before running anything in it
	@$(COMPOSE) build backend

build-frontend-test: ## Refresh the frontend test image
	@$(COMPOSE) --profile test build frontend-test

up: ## Start backend + frontend in the background
	$(COMPOSE) up --build -d

demo: ensure-artifacts ## Build and run the full stack in the foreground
	$(COMPOSE) up --build

down: ## Stop everything and remove orphaned containers
	$(COMPOSE) down --remove-orphans

restart: down up ## Recreate the stack

logs: ## Follow logs from the running stack
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

shell: ## Open a shell in the backend container
	$(COMPOSE) run --rm --no-deps backend sh

## ---------------------------------------------------------------- database

POSTGRES_USER ?= postgres
POSTGRES_DB ?= em_fusion

db-shell: ## psql into the running database
	$(COMPOSE) exec postgis psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db-reset: ## Drop the database volume and recreate it empty
	$(COMPOSE) rm -sf postgis
	docker volume rm -f em-fusion_postgis_data
	$(COMPOSE) up -d postgis

## ---------------------------------------------------------------- data

generate: ## Run the pipeline once, writing into DATA_DIR (default data/)
	mkdir -p "$(DATA_DIR)"
	$(COMPOSE) --profile pipeline run --rm \
		-v "$(abspath $(DATA_DIR)):/data" pipeline

ensure-artifacts: ## Generate the demo dataset only if artefacts are missing
	@if [ -z "$(strip $(ARTIFACTS))" ]; then \
		echo "No generated artefacts declared — nothing to build."; \
	elif [ -z "$(filter-out $(wildcard $(ARTIFACTS)),$(ARTIFACTS))" ]; then \
		echo "EM Fusion data artefacts are ready."; \
	else \
		echo "Data artefacts are missing; generating the deterministic dataset..."; \
		$(MAKE) generate DATA_DIR="$(DATA_DIR)"; \
	fi

## ---------------------------------------------------------------- quality

test: test-backend test-frontend ## Run backend and frontend test suites

# Every target below depends on its image being current. Compose bind-mounts
# the source but not site-packages, so a stale image runs today's code against
# yesterday's dependencies -- which fails confusingly when a dependency was
# added, and passes misleadingly when one was removed or changed. Make resolves
# a shared prerequisite once per invocation, so `check` rebuilds once, not five
# times, and a cached rebuild costs about a second.

test-backend: build-backend ## Pytest inside the backend container
	$(COMPOSE) run --rm --no-deps backend pytest $(PYTEST_ARGS)

test-frontend: build-frontend-test ## Vitest inside the frontend build stage
	$(COMPOSE) --profile test run --rm frontend-test

lint: build-backend build-frontend-test ## ruff (backend), Biome (frontend)
	$(COMPOSE) run --rm --no-deps backend ruff check app/ tests/
	$(COMPOSE) --profile test run --rm frontend-test pnpm lint

format: build-backend ## Black, then ruff's import sorting, against the mounted backend source
	$(COMPOSE) run --rm --no-deps backend sh -c "black app/ tests/ && ruff check --select I --fix app/ tests/"

type-check: build-backend ## mypy inside the backend container
	$(COMPOSE) run --rm --no-deps backend mypy app/

check: format lint type-check test ## Everything, in the order backend/Makefile uses

smoke: ## Health-check a running stack
	./scripts/smoke-test.sh

## ---------------------------------------------------------------- cleanup

clean: ## Stop the stack and drop its volumes, including the database
	$(COMPOSE) down --remove-orphans --volumes
