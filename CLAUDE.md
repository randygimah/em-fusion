# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

EM Fusion is a prototype for AI-assisted electromagnetic situational awareness: synthetic/replayed observations, explainable anomaly hypotheses, and human analyst validation. It is decision support, not autonomous decision-making.

Development is deliberately incremental — see `implementation.md` for the phase-by-phase build checklist (currently mid-way through Phase 3, Operational Picture Layout). Only `frontend/` has real code today. `backend/`, `ai/`, `docs/`, `infrastructure/`, and `scenarios/` are empty placeholders reserved for the planned FastAPI backend, ML/classification code, docs, Docker/deploy configs, and scenario fixtures respectively (see `em_fusion.md` section 21 for the target layout, and section 12 for the intended tech stack: FastAPI/Pydantic/SQLAlchemy/PostGIS on the backend).

`em_fusion.md` is the full project scope/PRD (data sources, fusion engine, hypothesis engine, DB design, milestones, v2 roadmap). `DESIGN.md` is the design system spec (colors, typography, spacing, component styling) — front-matter contains the raw design tokens.

## Commands

Package manager is pnpm (requires Node >= 22.13; run `nvm use v24.14.0` first if on an older default). All commands run from `frontend/`:

- `pnpm install` — install dependencies
- `pnpm dev` — start Vite dev server (port 1234, proxies `/api` to `http://localhost:8080`)
- `pnpm build` — typecheck (`tsc -b`) then production build
- `pnpm lint` — ESLint
- `pnpm test` — run Vitest once (CI mode)
- `pnpm test:watch` — Vitest watch mode
- Single test file: `pnpm exec vitest run src/test/operationalPicture.test.tsx`

## Architecture

The frontend is a contract-first React app: UI components are dumb renderers that accept a typed data prop, decoupled from where that data comes from.

- `src/types/operationalPicture.ts` — the `OperationalPicture` contract (scenario, hypotheses, detectionSummary, rfSensors, aircraftTracks, timelineEvents). This type is meant to mirror the future FastAPI `/operational-picture` response shape exactly.
- `src/mocks/operationalPictureMock.ts` — a mock object satisfying that contract, currently the app's only data source.
- `src/screens/operationalPicture.tsx` — the main screen; receives `operationalPicture: OperationalPicture` as a prop rather than importing the mock directly, so it can later take real API data with no change to the component.
- `src/App.tsx` — wires the mock into the screen; this is the seam where a real API call will replace the mock import.
- `src/components/em/` — shared UI primitives prefixed `Em*` (e.g. `EmButton`), built with `class-variance-authority` (`cva`) for variants and `cn` (`src/lib/utils.ts`, `clsx` + `tailwind-merge`) for class merging. Follow this cva+cn pattern for new styled components.
- Tailwind v4 is wired via the `@tailwindcss/vite` plugin (no separate `tailwind.config.js`); colors/spacing/type scale should follow the tokens in `DESIGN.md` rather than ad hoc values.
- A `MapView` boundary component (not yet built) is intended to be the only place Mapbox GL JS is touched, so it can be mocked in tests and the rest of the app stays map-library-agnostic.

## Testing conventions

- Tests live in `src/test/` (Vitest + Testing Library + jsdom), not colocated with components, with one legacy exception (`src/App.test.tsx`).
- Assert on analyst-visible behavior (rendered text/values from the data contract), not implementation details like CSS classes.
- Render tests against the mock data module so assertions can reference `operationalPicture.*` fields directly instead of duplicating literals.

## Git

- Do not add a `Co-Authored-By:` trailer to commit messages.
