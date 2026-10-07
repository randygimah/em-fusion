# EM Fusion

EM Fusion is a prototype for AI-assisted electromagnetic situational awareness. Version 1 focuses on a safe decision-support workflow: synthetic/replayed observations, explainable hypotheses, and human analyst validation.

Development is intentionally incremental. See [docs/implementation.md](docs/implementation.md) for the v1 learning checklist and phase-by-phase workflow.

## Quick start

Everything runs through Docker Compose, driven by the root `Makefile`:

```bash
make          # list every target
make up       # build and start backend + frontend in the background
make dev      # backend + Vite dev server over the working tree, hot reload on :1234
make smoke    # check both services, and that the frontend can reach the backend
make down     # stop everything
```

| URL | What |
|---|---|
| http://localhost:8080 | Frontend (nginx, serving the built React app — shows an edit only after a rebuild) |
| http://localhost:1234 | Frontend dev server, after `make dev` — serves the working tree and reloads on save |
| http://localhost:8000/api/v1/health | Backend health endpoint |
| http://localhost:8000/docs | Generated OpenAPI documentation |
| localhost:5432 | PostgreSQL 15 + PostGIS 3.5 (`make db-shell`) |

The frontend proxies `/api/` to the backend, so a browser only ever needs port 8080 (or 1234 under
`make dev`). The backend container already reloads on save. Stop any host `pnpm dev` before `make dev`:
both want port 1234, and `localhost` may reach the host one.

### Common targets

| Target | Does |
|---|---|
| `make demo` | Build and run the stack in the foreground |
| `make test` | Backend pytest and frontend Vitest, both in containers. Starts PostGIS and provisions the test database first, so the database-backed tests actually run |
| `make migrate` | Apply the Alembic revisions to the running database |
| `make db-test-create` | Create the disposable `test_em_fusion` database with PostGIS. Idempotent; `make test` depends on it |
| `make lint` / `make type-check` / `make format` | ruff + Biome / mypy / black + ruff |
| `make check` | All of the above, in the order `backend/Makefile` uses |
| `make generate` | Run the data pipeline once into `data/` (not yet implemented) |
| `make db-shell` / `make db-reset` | psql into the database / drop its volume and recreate it empty |
| `make logs` / `make ps` / `make shell` | Follow logs / container status / shell in the backend |
| `make clean` | Stop the stack and drop its volumes |

## Running without Docker

Both halves run natively if you prefer. Node >= 22.13 (`frontend/.nvmrc` pins it) and Python >= 3.11.

```bash
# frontend — Vite dev server on :1234, proxying /api to :8000 (API_PROXY_TARGET overrides)
cd frontend && pnpm install && pnpm dev

# backend — uvicorn on :8000
cd backend && uv sync && cp .env.example .env
uv run --env-file .env uvicorn app.main:app --reload --port 8000
```

**The backend needs `DATABASE_URL` set to start.** It is read from the environment only, has no
default, and a missing or empty value fails at startup rather than at the first query — a fallback
connection string would let the service come up against the wrong database and report itself
healthy. Compose passes the variable to the `backend` and `pipeline` services already, so nothing is
needed there.

Running natively, note that **`backend/.env` is not read automatically**: only
`python -m app.corpus.build` calls `load_dotenv`, and `app.main` does not. A bare
`uvicorn app.main:app` fails at startup even with the file present. Use `uv run --env-file .env`
as above, or export the variable. The database itself does not have to be *reachable* for the app to
start: the engine is constructed without opening a connection, so `/api/v1/health` keeps answering
when the database is down, and a degraded database does not present as an unreachable service.

Backend dependencies live in `backend/pyproject.toml` and are pinned by `backend/uv.lock`; the lockfile is committed so a fresh clone reproduces the same environment. `backend/Makefile` holds the native lint/type/test commands.

## Database migrations

The schema is built by ordered [Alembic](https://alembic.sqlalchemy.org) revisions in
`backend/alembic/versions/`, applied oldest-first. Alembic records what it has applied in an
`alembic_version` table, so re-running is a no-op rather than an error.

```bash
cd backend
uv run --env-file .env alembic upgrade head    # apply
uv run --env-file .env alembic current         # what is applied
```

Three conventions, each load-bearing:

- **Revisions are written by hand; `--autogenerate` is not used.** It does not understand PostGIS
  geometry columns and would emit a revision nobody has read. New revisions are created with
  `alembic revision -m "..."` and filled in.
- **Migrations assert the PostGIS extension, they never create it.** `CREATE EXTENSION` needs
  superuser and is the container image's job on a fresh data directory. A migration that created it
  could never *fail* for its absence — and that failure is the point, because the alternative is a
  schema that builds fine and a first spatial query that dies with `type "geography" does not exist`
  a long way from the cause.
- **`alembic.ini` holds no connection string.** The URL comes from `DATABASE_URL`; a DSN in a
  committed file would be a credential in version control and would mean a stray `upgrade head`
  addressed a database nobody chose.

Spatial columns are stored as `geometry(..., 4326)` and cast to `::geography` at query time, so
distance is computed by PostGIS while the full geometry function set stays available.

### Running the database-backed tests

They are marked `database` and **skip unless `TEST_DATABASE_URL` is set**, which is what keeps the
unit suite runnable with no Docker:

In containers, `make test` handles all of it — it provisions the database and passes the variable, so
there is no manual step:

```bash
make test
```

Natively, provision once and pass the variable yourself. Note the host is `localhost` here and
`postgis` inside a container:

```bash
make db-test-create

cd backend
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/test_em_fusion \
  uv run pytest
```

`TEST_DATABASE_URL` is deliberately a **different variable** from `DATABASE_URL`. These tests drop
and recreate schema; pointing them at the application's own connection string would eventually run a
`DROP` against a database you cared about.

## The aviation corpus

The replayed telemetry is one hour of OpenSky state vectors, filtered to 49–54°N, 3–11°E. **Neither
the raw file nor the filtered extract is in this repository**: the OpenSky Data License Agreement
§3(iii) forbids making the data available outside the licensee's institute. What is committed is
`data/opensky/manifest.json` — source URL, snapshot hour, licence, attribution, and the SHA-256 of
the original — plus the tooling to rebuild from it.

A fresh clone reproduces the corpus in one command, once you accept the same terms:

```bash
cd backend && uv sync

# Set the pseudonymisation seed first — see below.
cp .env.example .env && $EDITOR .env

uv run python -m app.corpus.build --accept-licence
```

It prints the licence, downloads ~180 MB against the recorded checksum, filters to the box recorded
in the manifest, and writes `opensky_extract.parquet`, `manifest.json` and `coverage.json`. A file
already matching the checksum is kept rather than re-fetched, so re-running is cheap and idempotent.

`--box LAT_MIN LAT_MAX LON_MIN LON_MAX` overrides the recorded box; `--replace-corpus` is required
if the filtered extract no longer matches the recorded content checksum, because that means
replacing the corpus every recorded measurement was taken against.

### The pseudonymisation seed

`PSEUDONYM_SEED` in `backend/.env` is **a secret key, not a reproducibility value** — treat it like a
password:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Aircraft identifiers (`icao24`, `callsign`) are replaced with seeded pseudonyms at the Data
Abstraction Layer before anything is stored, as §3(i) requires for any disclosure. An `icao24` is
only 24 bits wide, so anyone holding the seed could reverse every pseudonym by exhaustive search —
which is why the seed is never committed and the manifest records only its SHA-256 fingerprint.

Set it once and do not change it: it determines every pseudonym in every figure. A different seed
produces a valid corpus with different labels, and all reported metrics still reproduce exactly,
because nothing downstream reads a pseudonym's value.

### The hosted model

The AI hypothesis layer has three producers, and only one of them costs money. Nothing in this
repository makes a real provider call except `backend/measurements/corpus/hosted_smoke_test.py`,
which refuses to run without an explicit opt-in.

`OPENAI_API_KEY` goes in `backend/.env` beside the seed, and is **never** committed — the template is
`backend/.env.example`. It is read from the environment by the adapter and never through a
configuration object, because generation parameters are persisted verbatim beside every hypothesis,
so a key held there would be written to the database once per row and into every backup of it.

**The key reaches the container through `backend/.env` on the bind mount, not through Compose.**
That is deliberate and the obvious alternative is a trap: Compose interpolates from the *host*
environment, so an unset variable arrives inside the container as an **empty string rather than as
absent**, and `load_dotenv(override=False)` treats present-but-empty as present — which would let
nothing shadow a perfectly good `.env`. `app/dal/pseudonymise.py` records the same trap for the seed
and clears an empty value before reading the file.

**Pin a dated model, never a moving alias.** The adapter refuses an identifier that does not end in
`-YYYY-MM-DD`: an alias changing mid-campaign invalidates the comparison with nothing in the results
saying so. Note that the provider's public price table lists aliases rather than identifiers, and the
dated ones it does show are legacy models that predate schema-constrained output — so the obvious
place to look yields exactly the models that cannot do the job. The authoritative list is the
provider's own model endpoint:

```bash
set -a; . backend/.env; set +a
curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -m json.tool | grep '"id"'
```

Currently pinned: **`gpt-4.1-2025-04-14`**. Chosen for the two properties the reproducibility claim
rests on — native schema-constrained output, and honouring `temperature` — rather than on price,
which is immaterial at this volume, or recency, which risks both. See `docs/qa.md` 94.

**Set a hard spending cap at the provider's own console, and turn auto-recharge off.** With prepaid
credits and no auto-recharge the balance itself is the hard cap, which is the guarantee wanted: a
limit that holds when the code is the broken thing. The in-code call budget is a second, nearer guard
that notices a retry loop in minutes rather than at the billing boundary — and it is held in memory,
so a process that dies and restarts counts from zero. Neither replaces the other.

A whole twenty-bundle scored campaign is about 33,000 input tokens for one arm. The minimum credit
purchase covers this project many times over.

#### The first real requests

```bash
make measure SCRIPT=corpus/hosted_smoke_test.py CORPUS=dev SMOKE_TEST_CONFIRM=yes
```

Three bundles, printed in full to be **read** rather than asserted on, before anything runs in bulk.
It is also what confirms which schema keywords strict mode actually accepts, which is provider
documentation this repository cannot verify on its own, and the only moment at which the estimated
cost can be compared against the provider's own billing while three calls are the account's entire
history.

## Layout

| Path | What |
|---|---|
| `frontend/` | React + TypeScript + Vite dashboard — the three analyst screens |
| `backend/` | FastAPI service; routes under `app/api/v1/` |
| `docs/` | Requirements, spec backlog, architecture model, and thesis notes |
| `ai/`, `infrastructure/`, `scenarios/` | Reserved, no code yet |

All new work follows spec → test → code. See [CLAUDE.md](CLAUDE.md) for the workflow and [docs/spec.jsonl](docs/spec.jsonl) for the backlog.
