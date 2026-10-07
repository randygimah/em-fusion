# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Agent instructions (read first, always follow)

**All new code follows the spec → test → code workflow below. No exceptions.** Do not write implementation code before a spec item exists and tests are written and proven to fail.

**Code is the source of truth.** Do not re-read source files you have already read in this session unless you have reason to believe they changed. Use the repo map below to navigate; read source files on demand when a task requires it. Design rationale lives in module docstrings, `docs/spec.jsonl` and `docs/thesis_notes.md` — not here.

**Read documents progressively.** The documents table below lists every doc and when to read it. Read a doc only when its trigger applies. Do not load all docs upfront.

**Keep the repo map current — and short.** Update the folder map and documents table whenever you add, remove, or rename a file that belongs there. A row says what a file is and any rule an editor must not break, in one to three sentences. Rationale and measurements go in the docstring, the spec item and `thesis_notes.md`, never in this file.

**Explain the item before building it.** Before starting work on any spec item — writing it or implementing it — give a short plain-English explanation in the chat: what the capability is for, what problem it solves, and how it connects to the rest of the app. Written for someone who does not know the codebase: no spec IDs carrying the meaning, no file paths, no function names. This is **output, not a document** — it goes in the reply, never into a file. It exists so the user understands what is about to be built while there is still time to redirect it, and the phrasing that survives usually becomes the `qa.md` entry and the progress-note paragraph later.

**Capture thesis material as you go.** See Thesis Notes below — findings, rationale, and references go into `docs/thesis_notes.md` while they are fresh, not at write-up time.

**Capture questions and clarifications as you go.** Every question the user asks, and every clarification that corrects a misunderstanding, gets appended to `docs/qa.md` in the same turn. See the Concepts Q&A section below.

**Keep the progress note current.** When a spec item lands that changes the story the progress note tells, offer to update it before moving to the next item. See the Progress Note section below.

## Project

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer, detects deviations deterministically, and turns evidence bundles into schema-validated, grounding-checked AI hypotheses for human analyst review. It is decision support, not autonomous decision-making. Confidence is always Low/Medium/High — never a percentage or decimal score — and that rule applies to any score shown in the UI.

Development is deliberately incremental — `docs/implementation.md` is the phase-by-phase checklist and `docs/handoff.md` says where the work stands now. **Phase order is amended** (Phase 5, the FastAPI contract mirror, runs before the Phase 3 view filter and Phase 4 playback); read the phase-order note at the head of the phase list before picking up work.

Scope is v2: exactly three screens (Operational Picture, Hypotheses, Scenario Control) — no TimescaleDB, no WebSockets (frontend polls), no multi-agent AI, no Isolation Forest/DBSCAN. Anomaly detection is deterministic only (threshold rules, rolling averages, z-score, PostGIS spatial clustering). The AI hypothesis layer is constrained: template generator first (fallback + evaluation baseline), then an AI generator, both schema-validated and grounding-checked before an analyst sees them.

## Repo Map

A contents page for the repo. Use it to find the right file before searching; it is not a substitute for reading the file.

### Folders

**`frontend/`** — React + TypeScript + Vite dashboard.

| Path | What's in it |
|---|---|
| `frontend/src/App.tsx` | The shell (nav rail + workspace switched on the route) and **the seam** — the only module that knows where a screen's data comes from. Each screen fetches inside its own route component. No screen imports a mock. |
| `frontend/src/routes.ts` | The three screens declared **once** (`nav-001`, `nav-003`): id, label, hash, icon path data, default, `screenFromHash`. An unrecognised hash resolves to the Operational Picture. |
| `frontend/src/hooks/useCurrentScreen.ts` | The route from the URL hash (`nav-001`). No router library. |
| `frontend/src/hooks/useRailCollapsed.ts` | Rail collapsed state (`nav-003`) in guarded `localStorage`, not the hash. Every storage access is wrapped; anything unexpected resolves to expanded. |
| `frontend/src/hooks/useOperationalPicture.ts` | The polling feed (`api-003`): picture plus `degraded`. A failed poll keeps what is on screen. Polls the pinned hour (`op-009`) under the selected view (`op-007`), refetching at once when either changes. |
| `frontend/src/hooks/useScenarioControl.ts` | Scenario Control feed (`api-010`): runs, `degraded`, accepted batch, `start`. **No fixture fallback**. |
| `frontend/src/hooks/useEvidenceCollapsed.ts` | Evidence panel collapsed state (`op-010`), same guarded-`localStorage` pattern as the rail; anything unexpected resolves to **expanded**. |
| `frontend/src/hooks/useEvidenceAccount.ts` | Evidence account for the hour on screen (`op-010`). Fetched per hour, never polled; a failed fetch does **not** keep the previous hour's answer. |
| `frontend/src/lib/api.ts` | **The only module that reaches the network** (`api-003`, `api-010`): endpoint paths, 5 s poll interval, fetch functions. `transport.test.ts` enforces this. |
| `frontend/src/lib/detectionVocabulary.ts` | Every finding type's wording in one module (`op-003`, `op-006`, `op-010`), plus grounding words and absence sentences. Panels must not carry their own vocabulary. |
| `frontend/src/lib/viewVocabulary.ts` | The view filter's words (`op-007`): the three options, the *Anomalous only* default, the showing/switching line, and what an emptied grid or timeline says it withheld. `op-004` inherits them. |
| `frontend/src/lib/scenarioLibrary.ts` | The five scenario types and descriptions (`api-010`). Not a mock — parity-checked against the backend enum. |
| `frontend/src/lib/utils.ts` | The `cn` helper (`clsx` + `tailwind-merge`). |
| `frontend/src/types/operationalPicture.ts` | The `OperationalPicture` contract, mirroring `/api/v1/operational-picture`; parity-checked from the backend suite. `detectionSummary` is nullable (null = no pass has run); `counts` carries typed absences. Each track's `state` (`api-016`) is `nominal` / `interrupted` / `unknown`, joined from stored gap findings — never re-detected, never a reportable claim. `view` (`api-007`) says which view was served, whether the hour was examined, and how many rows each collection withheld. |
| `frontend/src/types/scenarioControl.ts` | The Scenario Control contract (`scn-004`), parity-checked against the generator. |
| `frontend/src/types/evidence.ts` | The evidence contract (`api-015`, `op-010`), mirroring `backend/app/api/v1/schemas/evidence.py`. |
| `frontend/src/mocks/operationalPictureMock.ts` | Mock satisfying the picture contract; the first-paint fallback in `useOperationalPicture`. |
| `frontend/src/mocks/scenarioControlMock.ts` | **Test fixture only** (`api-010`) — nothing outside `src/test/` may import it; a test enforces that. |
| `frontend/src/screens/operationalPicture.tsx` | The main screen; takes `operationalPicture` as a prop. Detection Summary: a null summary renders a **sentence**, never a dash; only **reportable** counts are listed; a `null` count renders as a dash, never zero. The view control (`op-007`) labels the rows by the payload's `view.selected`, never by its own state, and anything a view empties says what it withheld from `view.suppressed`. |
| `frontend/src/screens/scenarioControl.tsx` | Scenario Control (`scn-004`): library, config form, run controls, status, recent runs. Controls disabled with a reason until a handler is supplied; `RESET`/`REPLAY` stay disabled (no endpoint). |
| `frontend/src/screens/hypotheses.tsx` | Placeholder destination naming what is missing until `hyp-*`. Replace it wholesale when `hyp-*` starts. |
| `frontend/src/components/em/` | Shared `Em*` primitives built with `cva` + `cn` (`EmButton`, `EmNavRail`, `EmEvidencePanel`, `EmLevel`, `EmDataModeBadge`, `EmSystemStatus`). `EmNavRail` renders entries as anchors with a collapse **button** (`nav-003`). `EmEvidencePanel` (`op-010`) has five states with five sentences and never falls silent; it collapses, and collapsed its header still counts the hour's conclusions and those with no stored evidence. |
| `frontend/src/main.tsx`, `frontend/src/index.css` | React entry; Tailwind v4 entry plus design tokens (no `tailwind.config.js`). |
| `frontend/src/test/` | All Vitest tests. **No coverage tooling** — frontend items are proved load-bearing by a mutation pass. |
| `frontend/src/App.test.tsx` | Legacy colocated test — the one exception to `src/test/`. Don't add more. |
| `frontend/src/assets/Design/*_v2/` | Generated design references per screen: `DESIGN.md`, `code.html`, `screen.png`. |

**`backend/`** — FastAPI app, Data Abstraction Layer, PostGIS persistence, detection, AI hypothesis layer, evaluation harness.

| Path | What's in it |
|---|---|
| `backend/app/main.py` | FastAPI app, CORS for Vite. Lifespan builds one Engine per process and **opens no connection** doing so. |
| `backend/app/pipeline.py` | Batch entrypoint (`scn-003`), `python -m app.pipeline` / `make generate`. Generates and deliberately does **not** score (`anom-016`). |
| `backend/app/replay.py` | Replay entrypoint (`adp-007`): archived corpus into the database. |
| `backend/app/api/v1/` | Route modules assembled by `api_router` (prefix declared once); handlers are prefix-free and hold **no SQL**, and may not import `sqlalchemy` or `alembic` (`db-006`). `health.py` (`api-001`, `ops-005`): 200 at expected schema revision, **503 when drifted**, 200 when the DB is unreachable. `operational_picture.py` (`api-012`; `view` parameter `api-007` — absent is `all`, unrecognised is 422, filtered in the payload builder and never in SQL), `scenario.py` (`api-006`: start and runs, no reset; launcher injected). |
| `backend/app/api/v1/schemas/` | Response schemas. `evidence.py` (`api-015`): the account of an hour's claims — explained / unexplained / unclaimed — matched on `claim_identity`, grouped on `(rule_id, finding_type)`. |
| `backend/app/dal/` | Data Abstraction Layer: `models.py` canonical observation, `validation.py`, `ingest.py` (single entrypoint for every adapter), `pseudonymise.py`, `repository.py` (the persistence **port**, imports no storage engine). |
| `backend/app/adapters/` | One module per source. `opensky.py` replay adapter (translation only). `synthetic_rf.py` (`adp-002`) synthetic RF driver; creates no run row. |
| `backend/app/db/` | Everything that knows PostgreSQL. `session.py`; `migrations.py` (`ops-005` schema-state comparison — expectation comes from the migration files, never the DB); `repository.py` (PostGIS port implementation, pass stamps, `quiet_run_ids`, `run_summary`, `schema_state`); `findings.py` (`db-008` findings, **replaced per run per rule** incl. at zero; `db-004` proximity in metres via geography; `db-009` clustering in EPSG:3035 with ordered window frames); `bundles.py` (`evb-002` citation resolution — exactly one row per ref; `db-011` refuses to replace bundles cited by hypotheses); `hypotheses.py` (`db-002` — **append, never replace**; three-valued grounding; `requested_generator` vs `generator` defines a fallback). |
| `backend/app/scenario/` | Configuration and generation. `layout.py` + `rf_layout.json` (`scn-005` sensor/channel layout — detectors hold no positions of their own); `emitter.py` (`scn-001` baseline, `RunSpec`, `BatchProvenance` per `scn-008`); `incident.py` (`scn-002` what a run stages + answer key); `tracks.py` (`scn-006` stages only on airborne aircraft, `scn-007` floor of 5 staged aircraft); `seeding.py` (the only source of invented numbers). |
| `backend/app/scenario/batch.py` | Runs a batch on a daemon thread (`api-006`) using the app's Engine, then **scores that batch's runs only** (`anom-016`) with one baseline per batch. Raises nothing. |
| `backend/app/scenario/guard.py` | **One batch at a time** (`api-011`): an in-memory lease, never persisted, claimed in the handler body (not a dependency) and released only by its holder. Sound only with a single uvicorn worker, which is asserted. |
| `backend/app/detection/` | Phase 8 — read `docs/detection_layer.md` first. `baseline.py` (`anom-002`), `rf_noise.py` (`anom-001`, `anom-014` 10 s minimum), `track_gap.py` (`anom-010`, intermediate not reportable), `clustering.py` (`anom-004`), `rate_excess.py` (`anom-012`), `sensor_fault.py` (`anom-007`), `fusion.py` (`anom-005`), `precedence.py` (`anom-013` ladder: SENSOR-FAULT, SOURCE-GAP, FUSION-SPATIAL), `latency.py` (`anom-009`, simulated time only), `sensitivity.py` (`anom-011`), `control.py` (`anom-008` quiet-run control), `bundle.py` (`evb-001` evidence bundle, every absence typed), `findings.py` (`db-008` canonical finding), `settings.py` (`anom-016` — the detector settings of record, pinned by a test; `anom-017` — `BASELINE_QUIET_RUNS`, the hundred quiet runs normal is measured over, each with its seed: declared, never read from the store). Pure: no database or network. |
| `backend/app/detection/chain.py` | The detection pass over one completed run (`anom-015`): composes the rules in `anom-013` order, takes normality as an input, persists track findings mid-chain, writes bundles first (`evb-003`), reported claims (`api-012`), and stamps the run last. Also `measure_normality`, which refuses a store not holding the pinned quiet runs as pinned (`anom-017`), and `assess_without_storing`, the same pass inside an always-rolled-back transaction — **a measurement writes nothing**, and only it may skip the bundle write. |
| `backend/app/ai/` | Phase 9 — read `docs/phase9_hypothesis_layer.md` first. `hypothesis.py` (`ai-001` output schema, nothing defaults), `template.py` (`ai-002` template generator — fallback and baseline, must not import any provider), `service.py` (`ai-003` port + result envelope; `GenerationConfig` carries no credential), `registry.py`, `fallback.py` (`ai-007`, blind to `ProviderUnavailable`), `budget.py` (`ai-009`), `payload.py` + `prompt.py` (`ai-004` egress and pinned prompt), `grounding.py` (`ai-008`), `assembly.py` (`ai-011`), `campaign.py` (`ai-012`). `providers/` is the **only** place a provider library may be imported (AST-checked). |
| `backend/app/evaluation/` | Phase 11 — read `docs/evaluation_harness.md` first. `sampling.py` (`eval-004` draw), `statistics.py` (`eval-005`, per arm, never pooled), `pack.py` (`eval-004`/`eval-007`/`eval-009` blinded scoring pack + glossary), `export.py` (`eval-003`), `metrics.py` (`eval-002`), `workbook.py` (`eval-008`). No database or model access. Every rate over an empty population is `None`, never 0.0. |
| `backend/app/corpus/` | Build-time tooling for the OpenSky extract: `fetch.py`, `extract.py`, `natural_gaps.py` (`adp-008` exclusion list), `python -m app.corpus.build`. Not part of the replay path. |
| `backend/alembic/` | Nine hand-written revisions (`0001`–`0009`). **Revision ids are the full file stem**; autogenerate is off (it does not understand PostGIS geometry). |
| `backend/tests/` | Pytest home. `fakes.py` in-memory repository; `conftest.py` shared DB fixtures and the **database guard** (refuses to wipe a DB holding more than a fixture could create); `contracts.py` parses the frontend TS contracts. Tests marked `database` skip unless `TEST_DATABASE_URL` is set. |
| `backend/measurements/` | The instruments behind every quoted figure, with committed logs: `corpus/` (needs DB + corpus; includes the two **billing** scripts and `rescore_baseline.py`, the one script that writes the store), `mutation/`, `extensibility/`, `exports/`, `superseded/`. Outside lint/type/test/coverage. Read `measurements/README.md` before quoting or re-running anything. |

**`docs/`** — all project documentation. See the Documents table below.

**Root tooling** — `compose.yaml` (six services: `postgis`, `backend`, `frontend`, plus profiled `pipeline`, `frontend-test` and `frontend-dev` — Vite over the mounted working tree for `make dev`, `ops-006`), the root `Makefile` (the single command surface over Compose — run `make` for the target list), and `scripts/smoke-test.sh` (post-start check that the services can reach each other and that PostGIS initialised).

**Empty placeholders** — `infrastructure/` (CI, deploy config) and `scenarios/` (scenario fixtures). The hypothesis and evaluation code live in `backend/app/`, not a root `ai/` folder, so they stay under the test suite, coverage gate, ruff and mypy.

### Documents

| Path | Read it when |
|---|---|
| `docs/handoff.md` | **Read first, at the start of every session.** Where the work stands. A snapshot, overwritten each session. See the Handoff section below. |
| `docs/requirements.md` | **Start here for "what must this do".** US-*, FR-*, NFR-*, out-of-scope, AC-*. Every spec item traces here. |
| `docs/spec.jsonl` | **The executable backlog** (`id`, `description`, `passes`). Read before starting any capability; write to it before writing tests. |
| `docs/em_fusion_v2.md` | The authority on technical detail (sources, architecture, DB, stack, out-of-scope, future work). The docx (not in repo) wins on academic framing. Read when a requirement or spec item is ambiguous. |
| `docs/research_scope.md` | Coding-relevant extract of the docx: research questions, evaluation metrics, success criteria. Read to check *why* a decision matters to the thesis. |
| `docs/implementation.md` | Phase-by-phase build checklist. Read to find what comes next and which phase an item belongs to. |
| `docs/detection_layer.md` | **Read before any `anom-*` work.** The detection layer on one page. Edited in place, never appended to. |
| `docs/evaluation_harness.md` | **Read before any `eval-*` work.** The evaluation harness on one page. Edited in place, never appended to. |
| `docs/phase8_detection.md` | Pre-build reasoning for Phase 8. Partly overtaken by measurement — `detection_layer.md` is current state. |
| `docs/phase8_evidence_bundles.md` | **Read before any `evb-*` work.** Pre-build reasoning for the evidence bundle builder. |
| `docs/phase9_hypothesis_layer.md` | **Read before any `ai-*` work.** Pre-build reasoning for the hypothesis layer: arm comparability, the two fallbacks, egress, cost, local-arm deferral. |
| `docs/thesis_notes.md` | **Write to it continuously.** Dissertation skeleton and evidence base. See Thesis Notes below. |
| `docs/qa.md` | **Write to it continuously.** Running Q&A on concepts. Explanatory, not authoritative. See Concepts Q&A below. |
| `docs/progress_note.html` | **The progress note's master copy.** Edit this, then publish it. See Progress Note below. |
| `docs/scoring_rubric.md` | **Pre-registered — do not edit after the campaign starts.** Blind hypothesis-scoring instrument. Read before `eval-004`/`eval-006`. Changes go in its change log with a reason. |
| `docs/architecture/workspace.dsl` | The C4 model, source of truth for every architecture diagram. Update it whenever a container, component, or external dependency is added or removed. |
| `docs/architecture/README.md` | How to view/validate/export the model (`structurizr local` on port 9090). |
| `docs/proposal_draft.md` | The submitted proposal. Framing only, not a build reference. |
| `docs/em_fusion.md` | **Superseded v1 PRD.** History only — never a scope reference. |
| `DESIGN.md` | Design system spec (tokens in front-matter). Read before writing any styled component; amend it when the build diverges. |
| `README.md` | Setup and run instructions. Update whenever setup, scripts, scope, or behavior changes. |
| `frontend/package.json`, `pnpm-lock.yaml`, `.nvmrc` | Scripts, dependencies, lockfile, pinned Node. |
| `frontend/biome.json`, `tsconfig*.json` | Biome lint/format; TypeScript project references. |
| `frontend/vite.config.ts`, `devProxy.ts` | Dev port 1234, `/api` proxy with no path rewrite, Tailwind plugin, Vitest setup. The proxy target comes from `API_PROXY_TARGET` via `devProxy.ts` (`ops-006`) — default `localhost:8000`, `backend:8000` in the container; never `VITE_`-prefixed. |
| `frontend/index.html`, `nginx.conf`, `Dockerfile` | Frontend build and container config. |
| `backend/Makefile` | Backend command surface (`format`, `lint`, `type-check`, `test`, `check`). |
| `backend/measurements/README.md` | **Read before quoting, re-running, or invalidating any figure.** Never print an aircraft identifier into a committed log; `PSEUDONYM_SEED` never appears. |
| `backend/pyproject.toml` | **Single source for dependencies and all tool config** (black/ruff/mypy/pytest). |
| `backend/uv.lock` | Pinned dependency graph. Committed. |
| `backend/.env.example` | Backend env var template. Secrets are never committed. |
| `backend/Dockerfile`, `.dockerignore` | Backend container config. |

## Spec-Driven Development — mandatory

Every new capability follows **explain → spec → test → code**, no matter how small. No implementation lands without a spec item and failing tests preceding it. If a change feels too small to spec, it still gets a spec item.

### 0. Explain

Say in plain terms what the item is for and how it links to what already exists, per the agent instruction above. No file is written at this stage.

### 1. Spec

Add one line per capability to `docs/spec.jsonl`:

```json
{"id": "anom-001", "description": "...", "passes": false}
```

- **`id`** — unique kebab-case slug, area-prefixed (`nav-`, `op-`, `ui-`, `map-`, `api-`, `db-`, `dal-`, `adp-`, `scn-`, `anom-`, `evb-`, `ai-`, `hyp-`, `fbk-`, `eval-`, `ops-`).
- **`description`** — inputs, outputs, constraints, **at least one failure case**, and references to other spec IDs, `FR-*`/`NFR-*`/`US-*`/`AC-*` requirement IDs, or doc files.
- **`passes`** — **always `false` when first written.** Set to `true` only after proving the tests pass.

**Get the user's agreement on spec items before proceeding to tests.**

Commit: `git commit -m "spec: add <id>[, <id>]"`

### 2. Test

Write unit tests only — frontend in `frontend/src/test/`, backend in `backend/tests/`.

- Every test includes a comment citing its spec ID, e.g. `// spec: anom-001`.
- **Write no implementation at this stage.**

Commit: `git commit -m "test: add tests for <id>[, <id>]"`

### 3. Prove the tests fail

Run them. **Every new test must fail.** A test that passes before the implementation exists is a wrong test — fix the test before continuing. Report the failure output; don't assert it happened.

### 4. Code

Implement the capability. Read relevant source files on demand rather than up front. **Ask the user for review after implementing each feature.** Do not set `passes: true` yet.

### 5. Prove the tests pass

All tests for the item must pass with **at least 90% coverage**. Fix failures before anything else. Only then set `"passes": true` on those items in `docs/spec.jsonl`.

Commit: `git commit -m "feat(<id>): <short-description> - tests pass"` — `feat`, `fix`, or `refactor` as appropriate.

## Commands

### Frontend

Package manager is pnpm (requires Node >= 22.13). `frontend/.nvmrc` pins the version — run `nvm use` from `frontend/` first if your shell's default Node is older. All commands run from `frontend/`:

- `pnpm install` — install dependencies
- `pnpm dev` — start Vite dev server (port 1234, proxies `/api` to `http://localhost:8000`)
- `pnpm build` — typecheck (`tsc -b`) then production build
- `pnpm lint` — Biome lint
- `pnpm format` — Biome format (writes)
- `pnpm test` — run Vitest once (CI mode)
- `pnpm test:watch` — Vitest watch mode
- Single test file: `pnpm exec vitest run src/test/operationalPicture.test.tsx`

### Backend

Python, managed with a venv (`backend/.venv`) and a Makefile. All commands run from `backend/`:

- `uv sync` (or `make install-dev`) — install dependencies from `uv.lock`
- `uvicorn app.main:app --reload --port 8000` — run the dev server
- `make format` — Black, then ruff import sorting (writes)
- `make lint` — ruff check
- `make type-check` — mypy
- `make test` — pytest
- `make check` — format + lint + type-check + test

## Architecture

### Frontend

*File-by-file locations are in the Repo Map above; this section is the rationale behind them.*

**Contract-first.** UI components are dumb renderers that accept a typed data prop, decoupled from where the data comes from. The contract types mirror the API response shapes exactly, screens take data as a prop, and `App.tsx` is the single seam that knows where data comes from — so changing a data source changes one file and no component.

**Styling.** Shared `Em*` primitives use `class-variance-authority` for variants and `cn` for class merging; follow that cva+cn pattern for new styled components. Tailwind v4 is wired through the `@tailwindcss/vite` plugin, so there is no `tailwind.config.js` — colors, spacing, and type scale come from the `DESIGN.md` tokens, not ad hoc values.

**Map boundary.** A `MapView` component (not yet built) is the only place MapLibre GL JS may be touched, so it can be mocked wholesale in tests and the rest of the app stays map-library-agnostic. MapLibre, not Mapbox: no account or access token, which keeps the data and presentation layers free of hosted dependencies — the hosted AI generator is the sole exception and the sole running cost.

**Navigation.** Exactly three entries: Operational Picture, Hypotheses, Scenario Control. System health is a compact strip in the nav footer, not a screen. Drill-down tables (full RF stream, full track inventory) are reached from panels on Operational Picture — they're cheap views over the same data, not separate screens.

**Transport.** No WebSockets. The frontend polls the FastAPI backend. Don't introduce push or streaming infrastructure.

### Backend

Stack per `docs/em_fusion_v2.md` §10: FastAPI, Pydantic, SQLAlchemy, PostgreSQL + PostGIS, Uvicorn, Pytest. No Celery or APScheduler. SQL and spatial logic belong in the repository layer (`app/db/`), never in route handlers.

## Testing conventions

- Frontend tests live in `frontend/src/test/` (Vitest + Testing Library + jsdom), not colocated with components, with one legacy exception (`src/App.test.tsx`). Backend tests live in `backend/tests/` (pytest; `pyproject.toml` sets `testpaths = tests`).
- Every test carries a comment citing the spec ID it proves, e.g. `// spec: op-004` or `# spec: dal-002`.
- Assert on analyst-visible behavior (rendered text/values from the data contract), not implementation details like CSS classes.
- Render tests against the mock data module so assertions can reference `operationalPicture.*` fields directly instead of duplicating literals.
- A correct non-detection is a first-class test, not an omission — see `anom-008` in `docs/spec.jsonl`.

## Thesis Notes

`docs/thesis_notes.md` is the skeleton and evidence base for the dissertation write-up. It is not a changelog and not a summary of the code — it is where the *reasoning* lives, captured while it is still fresh rather than reconstructed from git history months later. Treat keeping it current as part of the work, not as an afterthought.

### What goes in

- **Design rationale** — why a decision was made, what the alternatives were, and why they lost. Rejected options are as valuable as chosen ones; a decision with no recorded alternative reads as an accident.
- **Reversals** — when a decision is overturned, record the original position, the reason for the change, and what the reversal reveals. The reasoning behind a reversal is usually more useful to the write-up than either endpoint.
- **Measurements** — the third-adapter extensibility figures (files touched, lines changed, hours taken), `MapView` boundary diff size, grounding catch rates per arm, campaign cost and wall-time, detection metrics. Record the number *and* the conditions under which it was taken.
- **Threats to validity** — anything that could undermine a result: coverage gaps confounding ground truth, scoring-load limits, confounds in a comparison. Record these in advance of the analysis, not after.
- **References** — citations, licence and attribution requirements, dataset provenance, model IDs and versions, external sources consulted. Capture the full reference when first used; chasing a half-remembered source later is wasted time.
- **Limitations** — state them honestly and specifically. A named limitation is a stronger position than an unmentioned one.

### Structure

Four top-level sections, fixed: **Methodology**, **System Design and Architecture**, **Implementation**, **Evaluation**. Each carries an HTML comment listing what belongs there — read it before adding.

- Add a `###` subsection per topic with a descriptive title stating the decision, not the area (e.g. "Data acquisition: OpenSky static snapshot rather than the Trino interface", not "Data acquisition").
- Write prose in full sentences, not bullet fragments. This is draft dissertation text, not a scratchpad — the target is material that survives into the write-up with editing, not rewriting.
- Mark gaps explicitly with a parenthetical italic note, e.g. *(Record the bounding box chosen and the result of this check here once run.)* An acknowledged gap is actionable; a silent one is invisible.
- Cross-reference `docs/research_scope.md` for which research question a decision serves, and `docs/em_fusion_v2.md` for the technical detail, rather than duplicating either.

### When to write

- **When a decision is made** — immediately, in the relevant section, including decisions that were considered and rejected.
- **When a phase in `docs/implementation.md` completes** — offer to draft the matching section rather than leaving it.
- **When a measurement is taken** — with its conditions, before moving on.
- **When something goes wrong** — deviations, dead ends, and surprises are Implementation-chapter material, not embarrassments to omit.

## Concepts Q&A

`docs/qa.md` is the running record of everything that needed explaining. It exists because a concept explained once in conversation is lost at the end of the session, and the same confusion then costs the same time again — and because the places where understanding slipped are exactly the places the write-up will need to explain carefully to an examiner.

### What goes in

- **Every question the user asks**, whether about a domain concept, a technical mechanism, or a project decision.
- **Every clarification that corrects a misunderstanding** — including ones the user did not ask for, where an answer revealed a wrong assumption. State the wrong assumption plainly and then correct it; the correction is the valuable part and an answer without it reads as unmotivated.
- **Distinctions that were being conflated.** If two things were treated as one, name both and say what separates them.

Do not record decisions here. A decision and its rationale belong in `docs/thesis_notes.md`; `qa.md` explains what a decision *means*. Where the two touch, `qa.md` cross-references rather than duplicating, and `docs/em_fusion_v2.md` remains the source of truth.

### How to write it

- Append a new numbered `##` section. **Never rewrite or renumber an earlier answer** — if an answer is superseded by a scope change, add a new entry and note the supersession there.
- The heading is the question, in the user's own framing rather than a tidied-up version of it. The framing is part of the record.
- Lead with the direct answer in bold — **Yes**, **No**, **Essentially yes, but** — before the explanation.
- Use tables for anything enumerable, worked examples with real numbers for anything quantitative, and code blocks for anything structural.
- Close with limitations, traps, or threats to validity where they exist. Several entries carry a "worth recording as a limitation" note that feeds straight into the thesis.
- Add any new term to the glossary table at the foot of the file.

### When to write

In the same turn as the explanation. An entry written later is reconstructed from memory and loses the misunderstanding it was correcting, which is the part worth keeping.

## Progress Note

The progress note **EM Fusion in Plain English** — mastered at `docs/progress_note.html`, published on demand, **no URL tracked here** — is the third leg of the write-up material, and the only one written for someone outside the project. `thesis_notes.md` holds the reasoning and the rejected alternatives; `qa.md` explains what a decision *means*; the progress note tells the **story**, in plain English, with figures. Between them they are the raw material the dissertation is assembled from, which is why the note is kept current rather than reconstructed at write-up time.

### What goes in

- **The narrative thread.** What the system is for, what exists now, and how a reader gets from one to the other. Sections build on each other; a reader starts at the top and does not stop.
- **Worked examples on real data.** One record followed all the way through the machinery, with the actual values. Never composed figures — everything is a measurement or a count, reformatted for reading.
- **Figures where the geometry or the timing is the point.** Hand-authored inline SVG, drawn from real values (the bounding box, the two staleness clocks, the pipeline spine). A figure that restates the prose is decoration; a figure that shows something the prose cannot is the reason the format exists.
- **What it deliberately does not do yet**, in its own section, so nobody oversells what has been built.
- **Threats to validity**, stated in the plain-English form an examiner would need.

### What stays out

No spec IDs, no file paths, no function names, no commit hashes. A reader who has never opened the repository must be able to follow every sentence. Where the note and `thesis_notes.md` cover the same decision, the note says what it *means* and the notes say why it was *made* — the note is not a summary of the notes.

### When to update

- **When a spec item lands that changes the story** — a new source, a new stage of the pipeline turning from grey to solid, a measurement worth showing. Offer at the end of the item, before moving on.
- **When a figure it carries goes stale** — the pipeline spine and the progress-by-area table both encode current state and are the first things to rot.
- **When a number on it is superseded**, including by a correction. A figure that turns out to be wrong gets fixed on the note, not only in the notes.

### How to update

**Edit `docs/progress_note.html` — the master; a published page is a rendering of it.** Publish on demand and do not track a standing URL: a published artifact belongs to one account, so a fresh publish per session or account is intended. Keep the `<title>` and 📡 favicon stable. If a published page is ever ahead of the repo, read it back (`action: "read"`) and commit that before editing further.

## Handoff

`docs/handoff.md` is the bridge between sessions. Read it first, before anything else; write it at
the end of a session, or whenever asked. It is a **snapshot, overwritten each time** — not a log and
not a changelog. Git already records history; this records position.

Six sections, fixed, in this order:

| Section | Contents |
|---|---|
| **Goal** | What is being built. The project in a few sentences, then what this particular session set out to do. |
| **Current state** | Where the work stands *right now*. What is done, what is green, what is specified but unbuilt, what is blocked. Include measurements taken this session — the next session should not have to re-derive them. |
| **Files in flight** | The files being actively worked, and what the next step will do to them. If the tree is clean, say so. |
| **Changed** | What was touched this session: commits with their messages, files added or modified, new requirements, new dependencies. |
| **Failed attempts** | What was tried and did not work, and **why**. Wrong assumptions, misdiagnoses, reversals, corrections made by the user. This is the section that saves the next session from repeating the mistake. |
| **Next step** | What comes next, in order, and what gates what. Add anything open and unowned as a separate list below it. |

Rules:

- **Never invent content to fill a section.** If nothing failed, leave Failed attempts empty. An
  empty section is information; a padded one is noise that trains the reader to skim.
- **Record your own errors there, not just the code's.** A misdiagnosis, a guessed URL, a wrong claim
  corrected by the user — all of it goes in Failed attempts. The value of the file is proportional to
  how uncomfortable it is to write.
- **Be specific enough to act on.** Commit hashes, file paths, exact counts, exact checksums. "Fixed
  the tests" is useless; "32 passed, 99% coverage, `adp-004` still `passes: false` because the fetch
  entrypoint is unbuilt" is not.
- **Deviations from the workflow get recorded**, including tests written after implementation.

## Git

- Do not add a `Co-Authored-By:` trailer to commit messages.
- Commit message conventions per workflow stage are in the Spec-Driven Development section above: `spec: add <id>`, `test: add tests for <id>`, `feat(<id>): <description> - tests pass`.

### Working on `main`

This repo does not use feature branches or worktrees: work is committed directly on `main`, in the
spec → test → feat commit sequence above, and pushed so local and remote `main` stay in sync.
Independent spec items are still worked one at a time unless the user agrees otherwise.
