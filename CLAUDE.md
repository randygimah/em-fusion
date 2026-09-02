# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Agent instructions (read first, always follow)

**All new code follows the spec → test → code workflow below. No exceptions.** Do not write implementation code before a spec item exists and tests are written and proven to fail.

**Code is the source of truth.** Do not re-read source files you have already read in this session unless you have reason to believe they changed. Use the repo map below to navigate; read source files on demand when a task requires it.

**Read documents progressively.** The documents table below lists every doc and when to read it. Read a doc only when its trigger applies. Do not load all docs upfront.

**Keep the repo map current.** Update the folder map and documents table whenever you add, remove, or rename a file that belongs there.

**Capture thesis material as you go.** See Thesis Notes below — findings, rationale, and references go into `docs/thesis_notes.md` while they are fresh, not at write-up time.

**Capture questions and clarifications as you go.** Every question the user asks, and every clarification you give that corrects something they had misunderstood, gets appended to `docs/qa.md` as a numbered entry. Write the answer as it was actually needed — including the wrong assumption it corrected, because the correction is the useful part. Do this in the same turn as the explanation, not later. See the Concepts Q&A section below.

**Keep the progress note current.** When a spec item lands that changes the story the published progress note tells, offer to update it before moving to the next item. It is the third leg of the write-up material alongside `thesis_notes.md` and `qa.md`. See the Progress Note section below.

## Project

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer, detects deviations deterministically, and turns evidence bundles into schema-validated, grounding-checked AI hypotheses for human analyst review. It is decision support, not autonomous decision-making. Confidence is always Low/Medium/High — never a percentage or decimal score — and that rule applies to any score shown in the UI.

Development is deliberately incremental — see `docs/implementation.md` for the phase-by-phase build checklist (currently mid-way through Phase 3, Operational Picture Layout, 3-screen model). **Phase order is amended:** Phase 5 (FastAPI contract mirror) now runs before the Phase 3 view filter and Phase 4 playback, because both are server-side by specification and building them against a mock means building them twice. Read the phase-order note at the head of the phase list before picking up work. `frontend/` has the shell and the contract; `backend/` has the Data Abstraction Layer, the OpenSky replay adapter, the PostGIS schema and its repository, and `/api/v1/health` as its only route. `ai/`, `infrastructure/`, and `scenarios/` are still empty placeholders reserved for ML/classification code, Docker/deploy configs, and scenario fixtures respectively.

Scope is v2: exactly three screens (Operational Picture, Hypotheses, Scenario Control) — no TimescaleDB, no WebSockets (frontend polls), no multi-agent AI, no Isolation Forest/DBSCAN. Anomaly detection is deterministic only (threshold rules, rolling averages, z-score, PostGIS spatial clustering). The AI hypothesis layer is constrained: template generator first (fallback + evaluation baseline), then an AI generator, both schema-validated and grounding-checked before an analyst sees them.

## Repo Map

A contents page for the repo. Use it to find the right file before searching; it is not a substitute for reading the file.

### Folders

**`frontend/`** — React + TypeScript + Vite dashboard. The only part of the repo with substantial code.

| Path | What's in it |
|---|---|
| `frontend/src/App.tsx` | Wires the mock into the screen. **The seam** where a real API call replaces the mock import. |
| `frontend/src/main.tsx` | React entry point. |
| `frontend/src/index.css` | Tailwind v4 entry (no `tailwind.config.js`) plus design tokens. |
| `frontend/src/types/operationalPicture.ts` | The `OperationalPicture` contract — scenario, hypotheses, detectionSummary, rfSensors, aircraftTracks, timelineEvents. Mirrors the future `/api/v1/operational-picture` response shape. |
| `frontend/src/mocks/operationalPictureMock.ts` | Mock satisfying that contract. Currently the app's only data source. |
| `frontend/src/screens/operationalPicture.tsx` | The main screen. Takes `operationalPicture` as a prop; never imports the mock. |
| `frontend/src/components/em/` | Shared `Em*` UI primitives (`EmButton.tsx`) built with `cva` + `cn`. New styled components follow this pattern. |
| `frontend/src/lib/utils.ts` | The `cn` helper (`clsx` + `tailwind-merge`). |
| `frontend/src/test/` | Vitest home — `operationalPicture.test.tsx`, `setup.ts`. All frontend tests go here. |
| `frontend/src/App.test.tsx` | Legacy colocated test — the one exception to `src/test/`. Don't add more. |
| `frontend/src/assets/Design/OperationalPicture_v2/` | Generated design reference for screen 1: `DESIGN.md`, `code.html`, `screen.png`. |
| `frontend/src/assets/Design/Hypothesis_analysis_v2/` | Same, for screen 2 (Hypothesis Detail / Analyst Workbench). |
| `frontend/src/assets/Design/Scenario_control_v2/` | Same, for screen 3 (Scenario Control). |

**`backend/`** — FastAPI app, the Data Abstraction Layer, the PostGIS persistence layer, corpus tooling, and lint/type/test tooling.

| Path | What's in it |
|---|---|
| `backend/app/main.py` | FastAPI app, `/api/v1/health` only, CORS for the Vite dev server. Its lifespan builds the one Engine per process and disposes it. |
| `backend/app/__init__.py` | Package marker. |
| `backend/app/api/v1/` | Route modules, one per resource, assembled by `api_router` which declares the `/api/v1` prefix once. Handlers stay prefix-free. |
| `backend/app/dal/` | The Data Abstraction Layer. `models.py` is the canonical observation; `validation.py` accepts or rejects; `ingest.py` is the single entrypoint every adapter goes through; `pseudonymise.py` replaces source aircraft identifiers; `repository.py` is the **persistence port** — an interface, deliberately importing no storage engine. |
| `backend/app/db/` | Everything that knows about PostgreSQL. `session.py` (Engine, sessionmaker, per-request Session), `migrations.py` (Alembic config paths), `repository.py` (the PostGIS implementation of the DAL's port — all SQL and spatial logic lives here). |
| `backend/app/adapters/` | One module per source. `opensky.py` is the replay adapter: dialect translation only, no validation and no persistence. |
| `backend/app/corpus/` | Build-time tooling for the OpenSky extract — `fetch.py`, `extract.py`, and the `python -m app.corpus.build` entrypoint. Not part of the replay path. |
| `backend/alembic/` | Migration environment and `versions/0001_core_schema.py`, which creates all seven tables. Revisions are hand-written; autogenerate is off because it does not understand PostGIS geometry columns. |
| `backend/tests/` | Pytest home (`pyproject.toml` sets `testpaths = tests`). `fakes.py` holds the in-memory repository, kept alongside the PostGIS one so the unit tier needs no Docker. Tests marked `database` skip unless `TEST_DATABASE_URL` is set. |

**`docs/`** — all project documentation. See the Documents table below.

**Root tooling** — `compose.yaml` (five services: `postgis`, `backend`, `frontend`, plus profiled `pipeline` and `frontend-test`), the root `Makefile` (the single command surface over Compose — run `make` for the target list), and `scripts/smoke-test.sh` (post-start check that the services can reach each other and that PostGIS initialised).

**Empty placeholders** — reserved, no code yet:

| Path | Reserved for |
|---|---|
| `ai/` | AI hypothesis layer / evaluation code (per `docs/em_fusion_v2.md` §5.5, §5.9). |
| `infrastructure/` | Docker Compose, CI, deploy config. |
| `scenarios/` | Scenario fixtures (the five scenario types). |

### Documents

| Path | Read it when |
|---|---|
| `docs/handoff.md` | **Read first, at the start of every session.** Where the work stands: goal, current state, files in flight, what changed, failed attempts, next step. Overwritten each session, not appended to — it is a snapshot, not a log. See the Handoff section below. |
| `docs/requirements.md` | **Start here for "what must this do".** Numbered user stories (US-*), functional requirements (FR-*), non-functional requirements (NFR-*), out-of-scope list, and acceptance criteria (AC-*). Every spec item traces to a requirement here. |
| `docs/spec.jsonl` | **The executable backlog.** One JSON object per line: `id`, `description` (inputs, outputs, constraints, at least one failure case, cross-refs), `passes`. Read before starting any capability; write to it before writing tests. See the workflow section below. |
| `docs/em_fusion_v2.md` | The authority on technical detail: data sources, architecture, DB design, tech stack, milestones, out-of-scope list, future work. Wins over the docx on technical detail; the docx (`EM-Fusion-Project-Scope-v2.docx`, not in this repo) wins on academic framing and research questions. Read when a requirement or spec item is ambiguous. |
| `docs/research_scope.md` | The coding-relevant extract of the docx: research questions, objectives, architecture rationale, AI-layer validation/grounding detail, canonical data model, scenario types, evaluation metrics, success criteria. Read to check *why* a build decision matters to the thesis. |
| `docs/implementation.md` | The phase-by-phase build checklist and the current position in it (mid-Phase 3). Read to find what comes next and which phase a spec item belongs to. A learning checklist, not a rigid sprint plan. |
| `docs/thesis_notes.md` | **Write to it continuously, not just when read.** Dissertation skeleton and evidence base — Methodology, System Design and Architecture, Implementation, Evaluation. Every design decision, reversal, measurement, threat to validity, reference, and limitation goes here while fresh. See the Thesis Notes section below for what to capture and how to structure it. |
| `docs/qa.md` | **Write to it continuously, not just when read.** Running Q&A on concepts used elsewhere — RF/EM terms, OpenSky state vectors, the generator's determinism model, detection methods, bounding boxes, PostGIS, evaluation scoring. **Explanatory, not authoritative**: it paraphrases decisions rather than making them. When scope changes, update `em_fusion_v2.md` and re-check this follows. See the Concepts Q&A section below for what to append and when. |
| **The progress note** — <https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc> | **Not a repo file: a published artifact.** "EM Fusion in Plain English" — the project and everything built so far, explained with figures for a reader who knows none of it. Update it in place at that URL as items land. See the Progress Note section below. |
| `docs/scoring_rubric.md` | **Pre-registered — do not edit after the campaign starts.** The blind hypothesis-scoring instrument: Part A is the second scorer's handout (five dimensions, worded 1/3/5 anchors, worked example); Part B is method detail (corpus, weighted κ, adjudication rule, threats to validity). Read before touching `eval-004` or `eval-006`. Changes go in its change log with a reason, never a silent overwrite. |
| `docs/architecture/workspace.dsl` | **The C4 model, and the source of truth for every architecture diagram.** Four views: L1 System Context, L2 Containers, L3 Backend Components, and a local-Compose Deployment view. Level 4 is deliberately skipped. Update it whenever a container, component, or external dependency is added or removed — a stale diagram that still renders is the failure mode this file exists to prevent. |
| `docs/architecture/README.md` | How to view, validate, and export the model (`structurizr local` on port 9090, not 8080). Read before running Structurizr by hand. |
| `docs/proposal_draft.md` | The submitted project proposal. Read for the agreed framing; not a build reference. |
| `docs/em_fusion.md` | The **superseded v1 PRD**. History only. Its RF/IQ ML classifier, Isolation Forest/DBSCAN, WebSockets, and multi-screen nav are all cut from v2 — never use it as a scope reference. |
| `DESIGN.md` | The design system spec — colors, typography, spacing, component styling. Front-matter holds the raw tokens. Read before writing any styled component. |
| `README.md` | Setup and run instructions. Update it whenever setup, scripts, scope, or behavior changes. |
| `frontend/src/assets/Design/*/DESIGN.md` | Per-screen generated design references, alongside `code.html` and `screen.png`. Read when implementing that specific screen. |
| `frontend/package.json` | Scripts and dependencies. `frontend/pnpm-lock.yaml` is the lockfile; `frontend/.nvmrc` pins Node. |
| `frontend/biome.json` | Biome lint + format config. |
| `frontend/tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json` | TypeScript project references. |
| `frontend/vite.config.ts` | Vite config — dev port 1234, `/api` proxy to `:8000` with no path rewrite (the backend owns `/api/v1`), Tailwind plugin, Vitest setup. |
| `frontend/index.html`, `frontend/nginx.conf`, `frontend/Dockerfile` | Build and container config for the frontend. |
| `backend/Makefile` | The backend command surface (`format`, `lint`, `type-check`, `test`, `check`). Read before running backend tooling by hand. |
| `backend/pyproject.toml` | **Single source for dependencies and tool config** — `[project]` runtime deps, `[dependency-groups] dev`, plus black/ruff/mypy/pytest settings. No tool config lives outside it. |
| `backend/uv.lock` | Resolved, pinned dependency graph. Committed — it is what makes a fresh clone reproduce the environment a result was measured under. |
| `backend/.env.example` | Template for backend env vars. Secrets never get committed — add new keys here, not to a fixture. |
| `backend/Dockerfile`, `.dockerignore` | Backend container config. |
| `.claude/settings.local.json` | Local Claude Code permissions. Not project scope. |
| `.vscode/settings.json` | Editor settings. |

## Spec-Driven Development — mandatory

Every new capability follows **spec → test → code**, no matter how small. No implementation lands without a spec item and failing tests preceding it. If a change feels too small to spec, it still gets a spec item.

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

Implement the capability. Read relevant source files on demand rather than up front. **Ask the user for review after implementing each feature.** Do not set `passes: true` yet. Independent spec items may be worked in parallel — see Parallelism under Git below.

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

**Contract-first.** UI components are dumb renderers that accept a typed data prop, decoupled from where the data comes from. The `OperationalPicture` type mirrors the future `/api/v1/operational-picture` response shape exactly, screens take it as a prop, and `App.tsx` is the single seam where a real fetch replaces the mock — so swapping the data source changes one file and no component.

**Styling.** Shared `Em*` primitives use `class-variance-authority` for variants and `cn` for class merging; follow that cva+cn pattern for new styled components. Tailwind v4 is wired through the `@tailwindcss/vite` plugin, so there is no `tailwind.config.js` — colors, spacing, and type scale come from the `DESIGN.md` tokens, not ad hoc values.

**Map boundary.** A `MapView` component (not yet built) is the only place MapLibre GL JS may be touched, so it can be mocked wholesale in tests and the rest of the app stays map-library-agnostic. MapLibre, not Mapbox: no account or access token, which keeps the data and presentation layers free of hosted dependencies — the hosted AI generator is the sole exception and the sole running cost.

**Navigation.** Exactly three entries: Operational Picture, Hypotheses, Scenario Control. System health is a compact strip in the nav footer, not a screen. Drill-down tables (full RF stream, full track inventory) are reached from panels on Operational Picture — they're cheap views over the same data, not separate screens.

**Transport.** No WebSockets. The frontend polls the FastAPI backend. Don't introduce push or streaming infrastructure.

### Backend

The backend exposes `/api/v1/health` only today. Per `docs/implementation.md` Phase 5, next is `/api/v1/operational-picture` returning the same shape as the frontend contract, after which the frontend swaps its mock import for a fetch behind a small API function. Target stack per `docs/em_fusion_v2.md` §10: Pydantic, SQLAlchemy, PostgreSQL + PostGIS, Uvicorn, Pytest. The database is now running in Compose (`postgis` service, `DATABASE_URL` already passed to `backend`), but nothing connects to it yet — no Celery or APScheduler, a simple loop or on-demand replay is enough. SQL and spatial logic belong in a repository layer, never in route handlers.

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

The published artifact **EM Fusion in Plain English** — <https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc> — is the third leg of the write-up material, and the only one written for someone outside the project. `thesis_notes.md` holds the reasoning and the rejected alternatives; `qa.md` explains what a decision *means*; the progress note tells the **story**, in plain English, with figures. Between them they are the raw material the dissertation is assembled from, which is why the note is kept current rather than reconstructed at write-up time.

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

Republish **to the same URL** by passing it as `url` to the Artifact tool — publishing without it creates a second artifact and orphans the link. Keep the `<title>` and favicon stable across updates. The source file lives in the session scratchpad, so a new session re-reads the published page (`action: "read"`) before editing rather than rebuilding it from scratch.

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

### Branches and worktrees

Agent work happens on branches, isolated using git worktrees.

Start a branch:

```bash
git worktree add .worktrees/<id> -b <id>
```

Finish a branch:

```bash
# 1. Inspect the diff before merging
git fetch origin main
git diff main...<id> -- <changed-files>

# 2. Deconflict any overlap, amend the branch commit if needed

# 3. Merge, push, clean up
git checkout main
git merge --no-ff <id> -m "merge: <id> — <short description>"
git push origin main
git worktree remove .worktrees/<id>
git branch -d <id>
```

Local and remote `main` must be in sync after every merge.

### Parallelism

Spec items with no shared file or data dependencies may be coded in parallel.

- **Present the parallelism plan to the user first** — which items, and why they are independent — and get agreement before spawning sub-agents.
- Each parallel item gets its own worktree and branch.
- Deconfliction happens at merge, per the sequence above.
