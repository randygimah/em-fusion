# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

Two items this session, and between them they close the question that reframed the roadmap two
sessions ago — *does detector output on injected anomalies show in the app at all?* It does now,
and a user has seen it.

**`anom-016`, the detection pass fires when a generation batch completes.** `anom-015` built the
pass and `api-012` built the screen that renders it, and nothing called the pass. Its real cost was
not the trigger: **the detector settings every figure of record was measured under lived only in a
measurement script**, plus a copy in the test suite, so a trigger inside the application would have
had to declare a third set with the same standing as the other two.

**`ops-005`, the health signal refuses when the schema is behind the code**, found while
re-examining the stored runs. `0009` had been applied to the test database by the fixture that
brings it to head and never to the application's, so `/api/v1/operational-picture` returned **500
for a day** while 1,874 tests passed over those columns and the container reported itself healthy.

## Current state

Backlog **74 of 108** (`anom-016` and `ops-005` are new; `api-001` amended and still passing).

- Backend: **1895 passed, 99.92% total coverage, exit 0**, in containers (1830 and 99.83% at the
  start of the session).
- At **100%**: `app/detection/settings.py` (15 statements), `app/scenario/batch.py` (68),
  `app/db/migrations.py` (43), `app/api/v1/health.py` (14).
- `make lint`, `make format` and mypy clean (79 source files, was 78).
- Frontend untouched all session: no payload shape changed, only what the payload contains.
- **Seen on screen.** The user started a 20-run `gnss-degradation` batch from Scenario Control at
  11:18 on 2026-10-03; it generated in 83 s and the trigger stamped all twenty 30 s later. Run 420
  now serves anomaly **High**, integrity **Medium**, one `possible_interference_zone`, two of seven
  receivers **deviating**, one timeline event. Verified in the browser as well as in the payload.
- Mutation, `anom-016`: **28 of 29 valid killed, no unexpected survivors**, one proven equivalent
  declared
  in advance (`measurements/mutation/mutate_anom016_batch_trigger.log`). **0 test changes, 0
  implementation changes** — the first pass here to need neither, which is attributable to the
  two corrections the red run had already forced out. Its first attempt aborted on its own
  sentinel: see Failed attempts.
- Mutation, `ops-005`: **19 of 19 killed, no survivors**, after a first pass killed 18 and left one
  real gap (`measurements/mutation/mutate_ops005_schema_drift.log`). 1 test added, 0 implementation
  changes.

### `ops-005`: what the guard does, and the shape of its constraint

| | |
|---|---|
| Where | The health route — because that is what the container probe reads, and it said healthy all day |
| Why not a startup gate | The lifespan opens no connection on purpose, so a database that is down does not stop the service coming up. Determining a revision needs one |
| At the expected revision | 200, `at-head`, revision named |
| Drifted (behind, ahead, never migrated, two heads) | **503**, naming the revision found *and* the one expected |
| Unreachable | **200**, `unknown` — an outage is not a misconfiguration |
| Caching | Expectation cached for the process's life (cannot change without a restart); the database's revision read **every probe** (a live migration must clear the refusal without one) |
| Also | `up` and `demo` migrate first, amending `ops-003` — a guard that fires on every first run is one somebody switches off |

Proved live against a scratch database rather than the corpus: 503 with
`"this database has never been migrated"`, then 200 on the next probe after migrating it with the
container still running. Scratch database dropped, throwaway containers removed, all 400 runs still
stamped.

### The store, after today

| | |
|---|---|
| Completed runs examined | **380 of 380** in 6.2 min at 0.99 s a run, no refusals, no failures |
| Stamped | 0 before, 380 after, none left |
| Distinct settings records across the store | **1** |
| Reproduces `eval-002`? | **Exactly** — 60/60 on all three positive arms, 0/60 on both negative arms, diagonal matrix |
| `/api/v1/operational-picture` | **200**, serving a scored payload (was 500) |

Three batches, which matters because the screen shows the newest: 20 quiet runs from 30 September
(ids 381–400, what the screen serves), 300 corpus v2 runs (81–380), 60 dev-batch runs (21–80). The
re-score is baselined over corpus v2's **60** quiet runs via `_corpus.quiet_runs`, not the store's
100, so the stamps match the provenance every quoted figure was taken under — and that is a
deliberate difference from what the application itself does, recorded in `measurements/README.md`.

0.99 s a run against 1.22 s on record: same code, same hours, warm caches across a 380-run sweep.
**1.22 s stays the figure to quote for a single run.**

### What the item actually does

| | |
|---|---|
| Where scoring lives | `run_batch_now`, after `run_batch` returns. `app/pipeline.py`'s `main()` calls `run_batch` directly, so `make generate` is unscored **by construction** |
| Which runs | only this batch's completed runs, from `BatchSummary.runs` — never the store |
| Baseline | one per batch, over the store's completed `normal-baseline` runs |
| Settings | `POLICIES_OF_RECORD`, from the new `app/detection/settings.py` |
| On failure | per-run recorded and skipped; whole-batch refusal reported separately; nothing raises out |
| Cost | 11.2 s baseline + 1.22 s a run ≈ 35 s on a twenty-run batch |

### The three things worth knowing

**Eleven numbers were homeless, not thirteen.** The explanation given before the item was written
said "thirteen detector settings". Thirteen is a figure about what the *export* records. Four of the
six policy objects — the sensor-fault rule, the fusion rule, the precedence ladder and the
clustering rule — are taken at their defaults, and defaults have always lived in the package. What
existed nowhere in `app/` is `ThresholdPolicy`'s five required fields, `GapPolicy`'s two, and the
corpus box's four coordinates. The box was present only as a CLI `metavar`. That makes the finding
sharper: most of the record *was* in the right place, which is most of why nobody noticed the rest
was not.

**One definition plus one pin, which are different things.** Moving the values removes the copies
and leaves a change to them silent. So the eleven are also written out verbatim in a test — not a
fourth copy: a definition is what something runs under, a pin is an assertion about it. Elsewhere a
digest does this (`ai-004`'s prompt, `eval-003`'s provenance record); here a digest is unavailable
because the values themselves are what is pinned. A second test pins the other half — that four of
the six policies equal their own defaults — so a policy growing a required field makes the eleven
twelve visibly.

**Two paths that differ, asserted in both directions.** `python -m app.pipeline` built the 300 hours
behind every figure and must not score them, or the hours and the settings are welded together and
the same hours can never be re-read under another threshold. The guard walks the import graph —
and "the corpus command reaches no detector" is satisfied by a project with no detection at all, so
the positive direction is asserted beside it.

## Files in flight

None. The tree is clean.

## Changed

Commits, oldest first:

| Commit | Message |
|---|---|
| `2a39f0e` | `spec: add anom-016` |
| `d552cf7` | `docs: qa entry 143 — why the batch trigger needs the settings moved first` |
| `2a0f69c` | `test: add tests for anom-016` |
| `8c2dd58` | `feat(anom-016): the detection pass fires when a batch completes - tests pass` |
| `3c8a1ce` | `docs: anom-016 write-up` |
| `b8d48c9` | `docs: progress note for anom-016` |
| `74871c2` | `docs: stop tracking a progress-note URL in CLAUDE.md` |
| `4587f9c` | `measure: examine every stored run with the detection pass` |
| `8eab340` | `docs: the re-score, and three findings from it` |

**New files**

- `backend/app/detection/settings.py` — the eleven values, with the box here rather than in
  `app/corpus/` because what reads it is a detector.
- `backend/tests/test_anom_batch_trigger.py` — 42 cases.
- `backend/measurements/mutation/mutate_anom016_batch_trigger.py` + `.log`.

**Changed, backend**

- `app/detection/chain.py` — `measure_normality`. Takes the metric from the policy the deviation
  will be read against, and refuses an empty run list with its own message.
- `app/db/repository.py` — `quiet_run_ids` (completed `normal-baseline` runs, ordered, empty rather
  than raising) and `run_summary` (one run as its row holds it, None when absent).
- `app/scenario/batch.py` — `BatchScoring`, `score_batch`, the call in `run_batch_now`, and the
  request schema moved behind `TYPE_CHECKING`.
- `measurements/corpus/detection_metrics.py` — imports the record and builds its baseline through
  `measure_normality`; its own observation reader is now dead and removed.
- `tests/test_anom_chain.py` — `POLICIES` is the record, and the threshold-moved test uses
  `dataclasses.replace` rather than restating four of the record's values.
- `tests/test_api_scenario.py` — the two launcher fakes return an empty `BatchSummary`.

## Failed attempts

**A refusal whose message was about the wrong thing.** `measure_normality` was written with no
refusal for an empty run list, on the reasoning that two already exist upstream —
`compute_rf_baselines` will not take an empty allowlist, `Normality` will not hold an empty
provenance. The test for the fresh-database case failed, and the reason is the finding: the refusal
that actually fires first is the baseline's, and it talks about an *allowlist an engine cannot
widen*, while the fact a caller needs is that **this store holds no quiet runs at all**. Since the
refusal reaches a log line and nothing else, the wording is the entire diagnostic. Three refusals
for one condition, each a different statement.

**I claimed thirteen settings were homeless and it is eleven.** Thirteen is `eval-003`'s export
floor count. Four of the six policy objects were already at their defaults inside `app/`. Corrected
before the spec item was written, and the spec says eleven.

**I asserted a batch takes ~105 s and could not source it.** The only figure on record is
`api-006`'s "roughly seventy seconds". The spec item now says that and says whose figure it is. The
105 came from somewhere in a previous session and survives nowhere.

**An import cycle that had never fired.** `app/scenario/batch.py` imports a request schema from
`app.api.v1.schemas.scenario`; importing anything under `app.api.v1` runs that package's
`__init__`, which imports the route module, which imports `app/scenario/batch.py`. The cycle has
existed since that module was written and never fired, because every path into it went through the
API package first. A test that imports the domain module directly is what surfaced it. Fixed by
moving the import behind `TYPE_CHECKING`, which it qualifies for — it is only ever an annotation.

**Two launcher tests broke, and the first instinct was wrong.** Both patched `run_batch` with a fake
returning `None`, which was faithful while the launcher ignored the return value. The tempting fix
was to stub `score_batch` out; that would have left those tests passing over a launcher whose new
half had been removed. The fakes now return what the real function returns — an empty
`BatchSummary`, which the scoring stage treats as nothing to examine.

**The mutation pass aborted on its own sentinel.** The sentinel set the radio threshold to 99 dB to
prove that source edits reach the tests. `ThresholdPolicy` refuses bands that do not increase past
the threshold, so the module raised on import, the suite reported `3 errors in 1.28s`, and the
harness refused to read that as a kill — correctly: a mutant killed by an import error is the
runtime twin of one that does not parse and says nothing about the tests. Two value mutants had the
same defect (swapping the two severity steps breaks the same rule) and were replaced with
single-step moves. Recorded as the eighth hazard in `measurements/README.md`, with the rule that a
mutation table over a *configuration* module is also a table of things that must stay
constructible — check by constructing each one first.

**And then I re-ran it from the wrong directory.** `cd backend` from a session already in `backend`,
so the pass never started and the stale log made it look like the same failure twice.

**A survivor whose shape is worth keeping: a test at each end of a chain is not a test of the
chain.** `ops-005`'s first mutation pass left one mutant alive. Two heads on disk was asserted on the
function that *reads* them and refused by the function that *compares* them, and nothing tested the
function between — so with two heads the expectation silently became whichever head sorted first,
and an unreachable database would have named a bogus expectation beside its *could not tell*. One
test closed it; no implementation change.

**My first health route imported a storage engine, and the purity guard refused it.** Only to
annotate a type — but `db-006` forbids a route module naming one at all, and the alias
`app.db.session` exports exists for exactly that. More useful is what the same check prevented: the
obvious implementation imports the Alembic configuration straight into the handler, which it also
forbids. The comparison went behind the repository port instead, which is where the rule already
said it belonged, and the `app.db` allowlist never widened.

**A test that passed on the host and failed only in the container.** `ops-005` asserts that the two
start commands migrate first, by reading the root Makefile — which is not in the backend image,
Compose mounting only `./backend`. The project had already solved this and I had not read far
enough: the Makefile is mounted read-only at `/repo/Makefile` for `test-backend`, and
`test_replay.py` checks both locations and **raises rather than skips** when it finds neither,
because a structural guard that silently does not run is a worse failure than the one it checks for.

**A migration applied to the test database and never to the application's.** `0009`'s two columns
were added by `api-012`; the suite's fixture brings the test database to head before every database
test, so 1,874 tests passed over them while the real database sat at `0008` and the endpoint that
reads them returned 500. Found today by querying the corpus before re-scoring it. The shape
generalises: a suite that creates its own schema tests the migration **and** hides whether anybody
has applied it elsewhere, and those two facts are indistinguishable from inside the suite.

**I measured 0.99 s a run and nearly replaced a figure of record with it.** It is the same work as
`anom-015`'s 1.22 s, measured differently — a 380-run sweep with warm caches rather than one run at a
time — so it describes a batch of 380 and not the single run the trigger performs. Both are now on
record with the conditions that produced them, and 1.22 s remains the per-run figure.

**`make measure` passes `CORPUS=""` when the variable is unset**, and `_corpus.which()` refuses the
empty string even though its own default is `v2`. The first re-score attempt died on that before
touching the database. Every measurement has to name its corpus explicitly; the default is
unreachable through the Makefile.

**`make test-backend` spent ten minutes rebuilding before running anything.** Not a defect, but the
first run looked hung. `test-backend-nobuild` exists for exactly this and is what the mutation pass
uses.

## Next step

1. **There is no way to ask the screen for a particular hour.** `api-002` serves the latest completed
   run, which was the right scope when nothing produced detection output. Every run in the store is
   now examined and the corpus holds 60 interference zones and 120 broken-receiver attributions, and
   none of them can be shown, because the newest batch is twenty quiet hours. Seeing a detection means
   generating a staged batch and letting the trigger examine it — currently the only path.
2. **Re-run the figures of record.** `detection_metrics.py` now imports the settings and builds its
   baseline through `measure_normality`. The values are unchanged and the equivalence is asserted at
   unit scale, and the re-score reproduced `eval-002`'s table exactly from stored rows — but
   `anom-015` validated its own refactor by reproducing all forty-three exported lines byte for byte,
   and that has not been done for this one.
3. **`op-003` and `op-006`**, the two panels `api-012` unblocked and that now have something to
   show. The summary panel is deliberately minimal and the timeline strip is not rendered at all.
4. **`hypotheses`**, the last producer-less field. 155 rows exist. Which arm an analyst sees,
   whether a row whose grounding check FAILED may be shown, and what `NOT_CHECKED` renders as.
5. **`eval-006`** still waits on a second rater, mid-October.

Open and unowned:

- ~~The progress note has not been updated for `anom-016`.~~ Updated and published 2026-10-02. Its pipeline spine now has a trigger and
  its "what it deliberately does not do yet" section should lose the entry saying nothing fires the
  pass. Offer before the next item.
- **`docs/thesis_notes.md` is misfiled from about line 6785 onwards.** Everything after `##
  Evaluation` is appended there regardless of chapter, so implementation findings — the allowlist
  that named a module, the concurrent suites, and now all seven `anom-016` entries — sit under
  Evaluation. Not corrected mid-item; worth one pass before write-up.
- A `normal-baseline` batch is scored against a baseline that includes its own runs, because the
  baseline is a property of the store and not of the batch. Same self-reference `anom-008`'s bands
  carry. Recorded rather than prevented; excluding the batch would mean a store holding one batch
  could not be scored at all.
- Nothing mechanical stops a **third** file declaring its own eleven values. The guard catches the
  regrowth of the two copies that existed, by parsing them; the pin catches a change to the values.
  A new file is caught by neither.
