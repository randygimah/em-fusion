<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-wordmark-dark.svg">
    <img src="docs/assets/logo-wordmark-light.svg" alt="EM Fusion" width="420">
  </picture>
</p>

<p align="center">
  <b>Explainable electromagnetic situational awareness, with a human making every call.</b><br>
  Real air traffic and simulated radio receivers, fused into one picture. Deterministic rules
  decide what is unusual; an AI writes an explanation the analyst can check; the analyst decides.
</p>

---

EM Fusion is a research prototype built for an MSc thesis. It replays a real hour of air traffic over the
Low Countries and western Germany alongside a simulated network of seven radio receivers, stages
incidents such as GNSS interference or a broken receiver, and asks three things: can such
different sources share one data model, can rules find what was staged, and can an AI explain what
the rules found without inventing anything.

**It is decision support, not an autonomous system.** Detection is rule-based and reproducible.
The AI only explains, and only from a sealed package of evidence the rules assembled. Every
citation it makes is checked against that package before an analyst sees it, and confidence is
only ever Low, Medium or High, never a percentage.

## The research questions

| | Question | Where it stands |
|---|---|---|
| **RQ1** | Can heterogeneous EM-relevant sources be normalised into one canonical model through a Data Abstraction Layer, and is that **measurably** extensible? | **Answered.** A third source was added late and measured: 2 new files, 1 existing file changed by registration only, nothing behind the abstraction touched. [Results](#rq1--adding-a-source) |
| **RQ2** | How well do baseline comparison and deterministic anomaly detection find deviations in synthetic RF and replayed movement telemetry? | **Answered** on 300 hours with a known answer key. [Results](#rq2--detection) |
| **RQ3** | Can a constrained AI layer produce explainable hypotheses without unsupported conclusions, and do they beat a template baseline? | **Built and run; blind marking in progress.** The grounding safeguard is measured; the quality comparison waits on the second marker. [Results](#rq3--explanations) |

## How it works

```mermaid
flowchart LR
  subgraph Sources
    OS["OpenSky hour, replayed<br/>133,634 state vectors"]
    RF["Synthetic radio grid<br/>7 receivers x 8 channels, every 10 s"]
    HL["Receiver health feed<br/>third source, RQ1"]
  end
  SC["Scenario generator<br/>seeded, five kinds of hour"] --> RF
  OS --> AD["Adapters<br/>one per source"]
  RF --> AD
  HL -.-> AD
  AD --> DAL["Data Abstraction Layer<br/>validate, stamp provenance, pseudonymise"]
  DAL --> DB[("PostgreSQL + PostGIS")]
  DB --> DET["Deterministic detection<br/>baselines, z-scores, spatial clustering,<br/>one decision ladder"]
  DET --> EVB["Evidence bundles<br/>every citation resolves to a stored row"]
  EVB --> TPL["Template generator<br/>baseline and fallback"]
  EVB --> LLM["Hosted LLM<br/>schema-constrained"]
  TPL --> CHK["Schema validation<br/>+ grounding check"]
  LLM --> CHK
  CHK --> API["FastAPI"]
  API --> UI["Analyst screens<br/>Operational Picture, Hypotheses,<br/>Scenario Control"]
  UI -- "verdict + note" --> API
  SC -. "answer key, never shown to the system" .-> EV["Evaluation harness"]
  DET --> EV
```

Every number the simulation invents comes from one seed, so any hour regenerates byte for byte. The
answer key of what was staged is written down at generation time and never reaches a detector, the
AI or the screen. Detection runs as one fixed ladder of questions:

<p align="center"><img src="docs/assets/readme/decision-ladder.svg" alt="A three-step ladder: is there a radio anomaly at all; is it one receiver only with clean neighbours; are aircraft dropouts unusually frequent nearby. Each yes or no leads to one of four answers." width="640"></p>

<details>
<summary><b>What a run is made of</b></summary>
<br>
<p align="center"><img src="docs/assets/readme/run-anatomy.svg" alt="A quiet run and a staged run side by side: the same real aircraft reports and the same invented radio grid, with a small patch altered in the staged run. The difference between the two is the answer key and nothing else." width="640"></p>
</details>

## What it looks like

<p align="center"><img src="docs/assets/readme/screen-interference.jpg" alt="The Operational Picture for one stored hour under the anomalous-only view: a 60 km dashed disc of possible interference between Eindhoven and the German border, two receivers deviating, interrupted aircraft, and the zone's pop-up with its receivers, window and Medium confidence." width="860"></p>
<p align="center"><sub>The Operational Picture, anomalous-only view: an hour with staged interference at two receivers, the zone the rule examined, and its evidence. Captured from the running system on 8 October 2026; the right-hand rail has since gained the hour's explanations.</sub></p>

<table>
<tr>
<td width="62%"><img src="docs/assets/readme/screen-all-traffic.jpg" alt="The same map under the all view: several hundred aircraft across the Low Countries and Germany, the seven receivers, and thinned labels."></td>
<td><img src="docs/assets/readme/screen-verdict-card.jpg" alt="The Hypotheses screen's right column: the explanation's affected area on a map, then the analyst verdict card with a note box and four buttons: Confirm, Reject, Needs more evidence, False positive."></td>
</tr>
<tr>
<td><sub>The same kind of hour under <i>All</i>: every replayed aircraft, the seven receivers, labels thinned so the important ones always show.</sub></td>
<td><sub>An explanation's affected area and the analyst's verdict card. The screen shows only what the store recorded.</sub></td>
</tr>
</table>

## Results

### RQ2 — detection

300 generated hours, 60 of each of five kinds, each scored against the answer key written when it
was generated. The full rule chain was re-run from the stored readings for this table.

| Kind of hour | Hours | Named correctly | Recall |
|---|---:|---:|---:|
| One broken receiver | 60 | 60 | 1.000 |
| Interference across several receivers | 60 | 60 | 1.000 |
| Mixed evidence (broken receiver + aircraft dropouts) | 60 | 60 | 1.000 |
| Quiet baseline: false alarms | 60 | **0** | — |
| Aircraft coverage gap (no rule can name it): false alarms | 60 | **0** | — |

Precision is 1.000 on both answers the system gives (120 of 120 and 60 of 60). Recall
depends on what is counted, so it is reported both ways: per hour it is perfect, but per disrupted
aircraft the rules flag 82% on interference hours and 59% on mixed-evidence hours. The
median time from incident start to complete evidence is 10 s for a broken receiver and 20 s for
interference, which needs a second receiver.

<p align="center">
  <img src="docs/assets/readme/recall-two-ways.svg" alt="Recall counted per hour and per aircraft: interference 1.000 and 0.823, mixed evidence 1.000 and 0.587, aircraft coverage gap no rule and 0.587." width="49%">
  <img src="docs/assets/readme/detection-delay.svg" alt="Delay per kind of hour: median 10 s for one broken receiver and mixed evidence, 20 s for interference; all between 10 and 90 s." width="49%">
</p>

**Read with care:** the incidents are synthetic and generated by the same project that detects
them, so these figures show the machinery is sound, not that it would hold on real interference.

### RQ3 — explanations

Two generators explain the same evidence package: a **template** (mechanical, the baseline and the
fallback) and a **hosted LLM** (`gpt-4.1-2025-04-14`, schema-constrained, temperature pinned).

| Measurement | Result |
|---|---|
| Grounding check on 41 real packages: honest citations wrongly flagged | **0 of 164** |
| Grounding check: deliberately corrupted citations caught | **164 of 164** |
| Scored campaign: packages drawn by a fixed seed | 20 |
| Explanations generated (LLM asked three times per package, plus the template) | 80 |
| Ungrounded citations found in those 80 | 0 |
| Campaign cost | £0.85 |

Quality is judged by **blind marking**: two markers score every explanation on a pre-registered
rubric without knowing which generator wrote it. The first marker has finished; the second is
under way, so **no quality comparison is reported yet**, by design.

<p align="center"><img src="docs/assets/readme/two-report-cards.svg" alt="Two report cards in series: the rules are graded against the answer key, and the explanations are graded model against template. Rules against model is never graded, because the model sees no readings and detects nothing." width="640"></p>

### RQ1 — adding a source

A third source, a feed of each receiver's temperature, supply voltage and uptime, was added late,
specifically to measure the cost. What would count as failure was written down first.

| What changed | Files | Lines added | Lines removed |
|---|---:|---:|---:|
| New code (generator and adapter) | 2 | 112 | 0 |
| Existing code: registering the new record type | 1 | 17 | 1 |
| New tests | 1 | 519 | 0 |
| Ingest, validation, pseudonymisation, storage port, schema, detectors, API, screens | **0** | — | — |

Detection results and the operational picture were proven identical with and without the new feed.
Active time was 17 minutes (2 hours elapsed, waits for review removed). That is a lower bound: it
was written by an AI coding agent that already knew the codebase, so the line count is the stronger
figure. On the generator side, adding an explanation provider costs 1 new module and 2 lines
elsewhere.

### Engineering evidence

- **Spec-driven:** 129 capabilities in [`docs/spec.jsonl`](docs/spec.jsonl), 120 done, each written
  with at least one failure case before its tests, and its tests proven to fail before any code.
- **Backend:** 2,368 tests, 99.90% line coverage, including live PostGIS tests.
- **Frontend:** 616 tests; instead of coverage, each screen is proven by **mutation testing**
  (deliberately broken copies that some test must catch).
- **Reproducible:** every quoted figure has a script and a committed log in
  [`backend/measurements/`](backend/measurements/README.md).

## The data

<table>
<tr>
<td width="40%"><img src="docs/assets/readme/corpus-box.svg" alt="The corpus box, 49 to 54 degrees north and 3 to 11 degrees east, about 309,000 square kilometres, with Hamburg, Schiphol, Düsseldorf, Cologne, Brussels, Frankfurt and Luxembourg marked."></td>
<td>

- **Real:** one hour of [OpenSky Network](https://opensky-network.org) state vectors, 27 June 2022
  12:00 UTC, filtered to 49–54°N, 3–11°E. Not redistributed (OpenSky licence §3(iii)); the repo
  holds a manifest with checksums and a one-command rebuild.
- **Pseudonymised at the front door:** aircraft identifiers are replaced with keyed pseudonyms
  before anything is stored.
- **Synthetic:** seven receivers at real airports (Schiphol to Köln-Bonn), eight GNSS L1 channels, a reading
  every 10 s, invented reproducibly from a seed. Five kinds of hour: quiet, broken receiver,
  interference, aircraft coverage gap, and mixed evidence.

</td>
</tr>
</table>

## What it deliberately does not do

- **Detect anything with AI.** The model explains; the rules detect.
- **Run live.** Replayed and synthetic data only; the frontend polls, with no streaming.
- **Claim real-world accuracy.** All incidents are simulated (see the caution under RQ2).
- **Name aircraft coverage gaps.** That rule was attempted twice and closed both times; the gap is
  reported as a limitation, not a zero.

## Stack

FastAPI, Pydantic, SQLAlchemy and Alembic over PostgreSQL 15 + PostGIS 3.5; React, TypeScript, Vite,
Tailwind v4 and MapLibre GL with an offline Protomaps basemap; pytest and Vitest; everything in Docker
Compose. Architecture model in C4 ([`docs/architecture/`](docs/architecture/README.md)).

## Quick start

Everything runs through Docker Compose, driven by the root `Makefile`:

```bash
make          # list every target
make up       # build and start backend + frontend in the background
make dev      # backend + Vite dev server over the working tree, hot reload on :1234
make basemap  # once: download the offline map (92 MB) and check it against its pinned checksums
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
| `make basemap` | Download the offline basemap — a Protomaps cut of the corpus box to zoom 10, a Europe overview to zoom 6, and their fonts and icons (92 MB) — into `frontend/public/basemap/` and check every file against `manifest.json`. Nothing is installed unless all 775 checksums match. Without it the map says the basemap could not be read and names this target |
| `make db-test-create` | Create the disposable `test_em_fusion` database with PostGIS. Idempotent; `make test` depends on it |
| `make lint` / `make type-check` / `make format` | ruff + Biome / mypy / black + ruff |
| `make check` | All of the above, in the order `backend/Makefile` uses |
| `make generate` | Run a scenario batch in a container, into the running database |
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
| `docs/` | Requirements, spec backlog, architecture model, and thesis notes; `docs/assets/` holds the logo and the README's figures |
| `infrastructure/`, `scenarios/` | Reserved, no code yet |

All new work follows spec → test → code. See [CLAUDE.md](CLAUDE.md) for the workflow and [docs/spec.jsonl](docs/spec.jsonl) for the backlog.
