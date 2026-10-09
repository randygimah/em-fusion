# EM Fusion — single command surface over compose.yaml.
# Backend-only tooling (black/ruff/mypy against a local venv) stays in
# backend/Makefile; everything here goes through Docker.

.DEFAULT_GOAL := help
.PHONY: help build build-backend build-frontend-test up demo dev down restart \
        logs ps shell db-shell db-reset migrate db-test-create \
        generate measure build-pipeline ensure-artifacts replay basemap \
        test test-backend test-frontend lint format type-check check smoke clean

COMPOSE ?= docker compose
DATA_DIR ?= data

# What `make generate` runs when nobody says otherwise (scn-003). A default is
# required rather than optional: a batch target that generated nothing usable
# on a fresh machine would satisfy AC-12 and leave the demo with an empty
# database. The base seed is a value, not a secret -- it is what makes the
# batch reproducible, and it is printed in the report either way. Override the
# whole set for a real campaign: `make generate PIPELINE_ARGS="..."`.
PIPELINE_ARGS ?= --scenario-type gnss-degradation --base-seed 20220627 --runs 20

# Kept deliberately in step with backend/Makefile's `test` target. The two run
# the same suite in different environments, and a coverage gate that applies in
# one but not the other means `make check` means two different things depending
# on where it was typed. CI (ops-002) calling one of them is what will stop this
# drifting again.
PYTEST_ARGS ?= --tb=short --cov=app --cov-report=term-missing --cov-fail-under=90

# Extra arguments for `replay`, e.g. REPLAY_ARGS="--window-seconds 60".
REPLAY_ARGS ?=

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

# The pipeline service builds its own image from ./backend rather than sharing
# the backend service's, so refreshing one does not refresh the other. Found by
# running `make generate` for the first time: the cached pipeline image
# predated SQLAlchemy becoming a dependency, and the batch died on an import
# before it reached anything of its own. This is the same stale-image failure
# the note above `test-backend` describes, in the one target that had no build
# prerequisite.
build-pipeline: ## Refresh the pipeline image before running a batch in it
	@$(COMPOSE) --profile pipeline build pipeline

# `ops-005`. Both start targets apply the migrations first, and `alembic upgrade
# head` against a database already at head is a no-op. The health route refuses
# when the schema is behind the code, which is the signal that was missing when
# `0009` reached the test database and not the application's -- and a guard that
# fires on every first run is one somebody switches off. Migrating from the
# container's own entrypoint is deliberately not the answer: `db-001` keeps
# migration a deliberate act, and an image that migrates on boot runs schema
# changes from however many instances start at once.
up: migrate ## Apply migrations, then start backend + frontend in the background
	$(COMPOSE) up --build -d

demo: ensure-artifacts migrate ## Apply migrations, then run the full stack in the foreground
	$(COMPOSE) up --build

dev: migrate ## Backend plus Vite's dev server over the working tree, with hot reload, on :1234
	@# ops-006. The backend already reloads on save; this adds the frontend half.
	@# --renew-anon-volumes: the container's node_modules is an anonymous volume,
	@# which would otherwise keep serving the previous install after a lockfile
	@# change while the image held the new one.
	$(COMPOSE) --profile dev up --build -d --renew-anon-volumes frontend-dev
	@echo "Dev server: http://localhost:1234 (logs: $(COMPOSE) logs -f frontend-dev)"

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

# The disposable database `db-001`'s tests run against. Deliberately a separate
# name *and* a separate variable from DATABASE_URL: those tests drop and
# recreate schema, so pointing them at the application's own connection string
# would eventually run a DROP against a database someone cared about. The host
# is the compose service, because this URL is used from inside a container.
TEST_POSTGRES_DB ?= test_em_fusion
TEST_DATABASE_URL ?= postgresql+psycopg://$(POSTGRES_USER):postgres@postgis:5432/$(TEST_POSTGRES_DB)

db-shell: ## psql into the running database
	$(COMPOSE) exec postgis psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db-reset: ## Drop the database volume and recreate it empty
	$(COMPOSE) rm -sf postgis
	docker volume rm -f em-fusion_postgis_data
	$(COMPOSE) up -d postgis

migrate: ## Apply the Alembic revisions to the running database
	$(COMPOSE) run --rm backend alembic upgrade head

# Idempotent by checking pg_database first, because `createdb` on an existing
# database exits non-zero and would fail every run after the first. The
# extension is created here rather than by a migration: `db-001` requires a
# *missing* extension to fail loudly at migration time, so the migrations
# assert it and something else has to install it. For the real database that
# is the image's init scripts, on a fresh data directory only.
db-test-create: ## Create the disposable test database with PostGIS
	$(COMPOSE) up -d --wait postgis
	$(COMPOSE) exec -T postgis psql -U $(POSTGRES_USER) -d postgres -tAc \
		"SELECT 1 FROM pg_database WHERE datname='$(TEST_POSTGRES_DB)'" \
		| grep -q 1 \
		|| $(COMPOSE) exec -T postgis createdb -U $(POSTGRES_USER) $(TEST_POSTGRES_DB)
	$(COMPOSE) exec -T postgis psql -U $(POSTGRES_USER) -d $(TEST_POSTGRES_DB) \
		-c "CREATE EXTENSION IF NOT EXISTS postgis"

## ---------------------------------------------------------------- data

# Deliberately the `backend` service, not `pipeline`. The pipeline service's
# command names `app.pipeline`, a module that does not exist until `scn-003`,
# so `replay` does not use it: pointing `replay` at that service would change
# what the service means. Mirrors `migrate` instead. (`generate` itself now
# works -- `app.pipeline` landed with scn-003.)
# DATA_DIR is mounted and --data-dir passed explicitly, rather than relying on
# the module default: inside the container the repository root above ./backend
# does not exist, so that default resolves to /data/opensky only by accident of
# where the mount lands. Same mount pattern as `generate`.
replay: ## Replay the archived corpus into the running database
	$(COMPOSE) run --rm \
		-v "$(abspath $(DATA_DIR)):/data" \
		backend python -m app.replay --data-dir /data/opensky $(REPLAY_ARGS)

# The command is spelled out rather than left to the service, because
# `compose run` replaces a service's command rather than appending to it, so
# PIPELINE_ARGS has nowhere to go otherwise. Same mount and --data-dir pattern
# as `replay`, and for the same reason: inside the container the repository
# root above ./backend does not exist.
generate: build-pipeline ## Run a scenario batch in a container, into the running database
	mkdir -p "$(DATA_DIR)"
	$(COMPOSE) --profile pipeline run --rm \
		-v "$(abspath $(DATA_DIR)):/data" pipeline \
		python -m app.pipeline --data-dir /data/opensky $(PIPELINE_ARGS)

# Every figure this project quotes comes from a script under
# backend/measurements, and until now every one of them was run by
# hand-writing a compose invocation -- which is exactly where a wrong
# environment variable gets supplied, and how the corpus came to be destroyed
# (see `ops-004`). `--no-deps` because a measurement reads the database that is
# already running and must never start an empty one beside it. No database URL
# is passed: the only one reachable here is the application's own, which is the
# right target for a measurement and the wrong one for anything that drops.
# SMOKE_TEST_CONFIRM and CAMPAIGN_CONFIRM are forwarded for the two scripts
# here that make real, billed provider calls -- corpus/hosted_smoke_test.py and
# corpus/scored_campaign.py; every other script ignores them. BACKFILL_CONFIRM
# is the third and is not about money: corpus/backfill_bundles.py is the only
# script here that WRITES to the store, re-examining up to 144 runs. Each script
# has its own variable rather than sharing one, so approving the three-bundle
# pre-flight can never also approve the twenty-bundle campaign, and neither can
# approve a corpus-wide write. RESCORE_CONFIRM is the fourth: corpus/rescore_baseline.py
# re-scores every completed run under the pinned baseline (anom-017). The credential
# is deliberately NOT forwarded: the script reads
# backend/.env through the bind mount, following app/replay.py rather than
# Compose interpolation, which turns an unset host variable into an empty string
# that would then shadow the file (see app/dal/pseudonymise.py).
measure: build-backend ## Run a measurement, e.g. make measure SCRIPT=corpus/bundle_end_to_end.py CORPUS=dev
	@test -n "$(SCRIPT)" || { \
		echo "SCRIPT is required, e.g. make measure SCRIPT=corpus/bundle_end_to_end.py"; \
		echo "see backend/measurements/README.md for what each one asks"; \
		exit 2; }
	$(COMPOSE) run --rm --no-deps \
		-e PYTHONPATH=/app -e CORPUS="$(CORPUS)" \
		-e SMOKE_TEST_CONFIRM="$(SMOKE_TEST_CONFIRM)" \
		-e CAMPAIGN_CONFIRM="$(CAMPAIGN_CONFIRM)" \
		-e BACKFILL_CONFIRM="$(BACKFILL_CONFIRM)" \
		-e RESCORE_CONFIRM="$(RESCORE_CONFIRM)" \
		backend python measurements/$(SCRIPT)

ensure-artifacts: ## Generate the demo dataset only if artefacts are missing
	@if [ -z "$(strip $(ARTIFACTS))" ]; then \
		echo "No generated artefacts declared — nothing to build."; \
	elif [ -z "$(filter-out $(wildcard $(ARTIFACTS)),$(ARTIFACTS))" ]; then \
		echo "EM Fusion data artefacts are ready."; \
	else \
		echo "Data artefacts are missing; generating the deterministic dataset..."; \
		$(MAKE) generate DATA_DIR="$(DATA_DIR)"; \
	fi

# map-001. The default basemap: a Protomaps cut of the corpus box to zoom 10,
# a Europe overview to zoom 6 drawn under it so the map never ends in grey,
# and the glyphs and sprite the style would otherwise fetch from a CDN, all
# served from the frontend's own origin. Only the manifest is committed. It is the single
# source of what is fetched (the URLs, box and zoom below are read from it, one
# field per line) and pins every file by SHA-256. Everything lands in .staging
# first and is moved into place only once every checksum matches, so a mismatch
# leaves the previous set, or none, never half of one.
BASEMAP_DIR := frontend/public/basemap
BASEMAP_MANIFEST := $(BASEMAP_DIR)/manifest.json
PMTILES_IMAGE ?= protomaps/go-pmtiles:v1.31.2
ALPINE_IMAGE ?= alpine:3.20
basemap_field = $(shell sed -n 's/^ *"$(1)": *"\{0,1\}\([^",]*\)"\{0,1\},\{0,1\}$$/\1/p' $(BASEMAP_MANIFEST))
basemap_box = $(shell sed -n 's/^ *"$(1)": *\[\(.*\)\],\{0,1\}$$/\1/p' $(BASEMAP_MANIFEST) | tr -d ' ')
BASEMAP_MOUNT = --user "$$(id -u):$$(id -g)" -v "$(CURDIR)/$(BASEMAP_DIR):/basemap"

basemap: ## Download the offline map and check every file against its pinned checksum
	rm -rf $(BASEMAP_DIR)/.staging && mkdir -p $(BASEMAP_DIR)/.staging
	sed -n 's/^ *{"path": "\(.*\)", "sha256": "\([0-9a-f]\{64\}\)"},\{0,1\}$$/\2  \1/p' \
		$(BASEMAP_MANIFEST) > $(BASEMAP_DIR)/.staging/SHA256SUMS
	@test -s $(BASEMAP_DIR)/.staging/SHA256SUMS || { echo "basemap: no checksums in $(BASEMAP_MANIFEST)"; exit 1; }
	docker run --rm $(BASEMAP_MOUNT) $(PMTILES_IMAGE) extract "$(call basemap_field,source)" /basemap/.staging/em-fusion.pmtiles \
		--bbox=$(call basemap_box,bbox) --maxzoom=$(call basemap_field,maxzoom)
	docker run --rm $(BASEMAP_MOUNT) $(PMTILES_IMAGE) extract "$(call basemap_field,source)" /basemap/.staging/europe-overview.pmtiles \
		--bbox=$(call basemap_box,overviewBbox) --maxzoom=$(call basemap_field,overviewMaxzoom)
	docker run --rm $(BASEMAP_MOUNT) -w /basemap/.staging $(ALPINE_IMAGE) \
		sh -c 'wget -qO- "$(call basemap_field,assets)" | tar -xzf - --strip-components=1'
	docker run --rm $(BASEMAP_MOUNT) -w /basemap/.staging $(ALPINE_IMAGE) \
		sh -c 'sha256sum -c SHA256SUMS > checked; s=$$?; grep -v ": OK$$" checked; exit $$s' \
		|| { rm -rf $(BASEMAP_DIR)/.staging; echo "basemap: a file does not match manifest.json -- nothing installed"; exit 1; }
	docker run --rm $(BASEMAP_MOUNT) -w /basemap $(ALPINE_IMAGE) sh -c 'cut -c67- .staging/SHA256SUMS \
		| while IFS= read -r f; do mkdir -p "$$(dirname "$$f")" && mv ".staging/$$f" "$$f"; done && rm -rf .staging'
	@echo "Basemap verified and installed in $(BASEMAP_DIR)."

## ---------------------------------------------------------------- quality

test: test-backend test-frontend ## Run backend and frontend test suites

# Every target below depends on its image being current. Compose bind-mounts
# the source but not site-packages, so a stale image runs today's code against
# yesterday's dependencies -- which fails confusingly when a dependency was
# added, and passes misleadingly when one was removed or changed. Make resolves
# a shared prerequisite once per invocation, so `check` rebuilds once, not five
# times, and a cached rebuild costs about a second.

# `--no-deps` is deliberately absent, and its absence is asserted by a test.
# It starts the backend container alone, so postgis never comes up, so every
# `database`-marked test skips -- and the target reports success over a suite
# that silently did less than it claims (ops-003, db-001).
#
# The root Makefile and compose.yaml are mounted read-only because
# tests/test_ops_command_surface.py and tests/test_replay.py assert against
# them, and Compose mounts only ./backend into the container. Same pattern as
# `generate`'s DATA_DIR mount. Those tests raise rather than skip when the
# mount is missing: a skip here would be the same failure mode they exist to
# catch, one level up.
test-backend: build-backend db-test-create ## Pytest inside the backend container
	$(COMPOSE) run --rm \
		-e TEST_DATABASE_URL="$(TEST_DATABASE_URL)" \
		-v "$(abspath Makefile):/repo/Makefile:ro" \
		-v "$(abspath compose.yaml):/repo/compose.yaml:ro" \
		-v "$(abspath frontend/nginx.conf):/repo/frontend/nginx.conf:ro" \
		-v "$(abspath frontend/Dockerfile):/repo/frontend/Dockerfile:ro" \
		-v "$(abspath frontend/public/basemap):/repo/frontend/public/basemap:ro" \
		-v "$(abspath .gitignore):/repo/.gitignore:ro" \
		-v "$(abspath frontend/src/types):/repo/frontend/src/types:ro" \
		-v "$(abspath docs/spec.jsonl):/repo/docs/spec.jsonl:ro" \
		backend pytest $(PYTEST_ARGS)

test-backend-nobuild: db-test-create ## Pytest with no image rebuild — for mutation passes only
	@# The backend service bind-mounts ./backend to /app, so a source edit is
	@# already visible inside the container and `build-backend` rebuilds an
	@# image whose source is overridden by the mount anyway. Skipping it turns
	@# a mutation pass from ~2.5 minutes per mutant into seconds, and removes
	@# the continuous Docker builds that exhausted memory and had the OOM
	@# killer stop two passes mid-run — leaving a mutant on disk.
	@#
	@# Use `test-backend` for everything else. This target does NOT pick up a
	@# dependency change, so run `make build-backend` once before a pass.
	$(COMPOSE) run --rm \
		-e TEST_DATABASE_URL="$(TEST_DATABASE_URL)" \
		-v "$(abspath Makefile):/repo/Makefile:ro" \
		-v "$(abspath compose.yaml):/repo/compose.yaml:ro" \
		-v "$(abspath frontend/nginx.conf):/repo/frontend/nginx.conf:ro" \
		-v "$(abspath frontend/Dockerfile):/repo/frontend/Dockerfile:ro" \
		-v "$(abspath frontend/public/basemap):/repo/frontend/public/basemap:ro" \
		-v "$(abspath .gitignore):/repo/.gitignore:ro" \
		-v "$(abspath frontend/src/types):/repo/frontend/src/types:ro" \
		-v "$(abspath docs/spec.jsonl):/repo/docs/spec.jsonl:ro" \
		backend pytest $(PYTEST_ARGS)

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
