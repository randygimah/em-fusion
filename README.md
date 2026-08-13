# EM Fusion

EM Fusion is a prototype for AI-assisted electromagnetic situational awareness. Version 1 focuses on a safe decision-support workflow: synthetic/replayed observations, explainable hypotheses, and human analyst validation.

Development is intentionally incremental. See [docs/implementation.md](docs/implementation.md) for the v1 learning checklist and phase-by-phase workflow.

## Quick start

Everything runs through Docker Compose, driven by the root `Makefile`:

```bash
make          # list every target
make up       # build and start backend + frontend in the background
make smoke    # check both services, and that the frontend can reach the backend
make down     # stop everything
```

| URL | What |
|---|---|
| http://localhost:8080 | Frontend (nginx, serving the built React app) |
| http://localhost:8000/api/v1/health | Backend health endpoint |
| http://localhost:8000/docs | Generated OpenAPI documentation |

The frontend proxies `/api/` to the backend, so a browser only ever needs port 8080.

### Common targets

| Target | Does |
|---|---|
| `make demo` | Build and run the stack in the foreground |
| `make test` | Backend pytest and frontend Vitest, both in containers |
| `make lint` / `make type-check` / `make format` | ruff + Biome / mypy / black + ruff |
| `make check` | All of the above, in the order `backend/Makefile` uses |
| `make generate` | Run the data pipeline once into `data/` (not yet implemented) |
| `make logs` / `make ps` / `make shell` | Follow logs / container status / shell in the backend |
| `make clean` | Stop the stack and drop its volumes |

## Running without Docker

Both halves run natively if you prefer. Node >= 22.13 (`frontend/.nvmrc` pins it) and Python >= 3.11.

```bash
# frontend — Vite dev server on :1234, proxying /api to :8000
cd frontend && pnpm install && pnpm dev

# backend — uvicorn on :8000
cd backend && uv sync && uvicorn app.main:app --reload --port 8000
```

Backend dependencies live in `backend/pyproject.toml` and are pinned by `backend/uv.lock`; the lockfile is committed so a fresh clone reproduces the same environment. `backend/Makefile` holds the native lint/type/test commands.

## Layout

| Path | What |
|---|---|
| `frontend/` | React + TypeScript + Vite dashboard — the three analyst screens |
| `backend/` | FastAPI service; routes under `app/api/v1/` |
| `docs/` | Requirements, spec backlog, architecture model, and thesis notes |
| `ai/`, `infrastructure/`, `scenarios/` | Reserved, no code yet |

All new work follows spec → test → code. See [CLAUDE.md](CLAUDE.md) for the workflow and [docs/spec.jsonl](docs/spec.jsonl) for the backlog.
