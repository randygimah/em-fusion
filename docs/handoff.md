# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session closed two items and, in answering one question, found the largest structural gap in
the project.

1. **`api-011`, one batch at a time** — a defect fix. Several starts in quick succession left the
   backend serving nothing at all.
2. **`eval-001`, the batch runner** — closed on a **measurement rather than code**.
3. **The question that reframed the roadmap:** *does detector output on injected anomalies show in
   the app at all?* No. Two new items were written in response.

## Current state

Backlog **70 of 106** — two items added, so the denominator moved. Tree clean.

- Backend: **1,757 passed at 99.92%** in containers; 1,470 locally. `make lint` and mypy clean.
- Frontend: **86 passed across 8 files, exit 0** (it exited non-zero before `api-011`).
- Mutation: **17 of 17** on `api-011` (`mutate_api011_guard.log`), no survivors.
- New measurement of record: `measurements/corpus/batch_reproducibility.log`.

### `api-011` — one batch at a time

The backend was found hung on `QueuePool limit of size 5 overflow 10 reached`, serving nothing, with
its container unhealthy. The cause is a **composition of two correct decisions**, each separately
tested: every start spawns an unbounded daemon thread (`api-006`), and every thread borrows the one
Engine (`db-003`). Together they compete with request serving for a pool whose ceiling is fifteen.

The measurement that shaped it says what it is **not**: one batch adds a single connection and
`/health` answers 200 throughout. So the remedy bounds the count rather than making a batch cheaper.

Five decisions worth keeping: nothing is written to the database (`db-007`'s argument — a batch
cannot outlive its process, so a persisted flag is a claim no crash can retract); a **lease** rather
than a flag, released in the batch thread's `finally`, because `launch_batch` returns in microseconds
and releasing there is not a weaker bound but the absence of one; release means *if I am still the
holder*, or a thread finishing late frees a bound a later batch holds; claimed in the handler body,
never in a dependency, so a 422 cannot consume it; and the wall clock, which is correct here and says
so because `anom-009` records the opposite mistake.

**Verified by hand in the browser** — the one check no test can make. A second Start Batch showed the
note naming the running batch and was accepted again once it finished. All 20 runs completed in 1m45s
(against the ~70 s quoted; different type, loaded machine, so treat 70 s as a floor), which means the
guard came back because the batch **finished** rather than died early.

It also closed an older defect: **the screen had no channel for a backend refusal at all.** The feed
has computed one since `api-010` and the seam dropped it, so every 422 was invisible.

### `eval-001` — closed on a measurement

The behaviour was built by `scn-003`. What never existed was the evidence: the item's only failure
case is a batch that cannot be reproduced from its recorded base seed, and until `scn-008` put that
seed **on the row** there was nothing to reproduce it from. So the case was **untestable rather than
failing** for as long as the item read as outstanding — a distinction a pass/fail backlog cannot
express, and the finding worth carrying into the methodology chapter.

| | |
|---|---|
| Runs re-deriving their own seed | **380 of 380** |
| Batches / base seeds | 19 / 5 — three for corpus v2, one development, one from the screen |
| Runs recording no batch | 0 |
| Batch sizes outside 20–30 | none |

The same measurement verifies, for the first time, the **seed-matching every matched-pair figure in
this project rests on** (`anom-006`'s sixty pairs, `anom-004`'s eight triples, `scn-007`'s forty):
**100 (base seed, index) positions, one to five arms at each, every position carrying a single seed
across all of its arms.** It follows from the derivation being keyed on base seed and index alone —
and a generator additionally keyed on the scenario type would leave every matched-pair figure
comparing unmatched runs with **no test failing**, because each run would still be internally
reproducible.

The item's fourth output clause, *detector output*, is **moved to `anom-015`** rather than met or
withdrawn. Running detection inside generation would couple a corpus to the detector policy —
`eval-003` records thirteen settings precisely because changing one moves every figure on the same
hours, so a corpus made at 6 dB could not be re-scored at 8 dB without regenerating 300 hours.

### The gap the question found

**Nothing the detection layer produces reaches the application.** Two independent failures: the
detectors never run in the shipped path (the rules execute only inside measurement scripts), and no
route carries their output anyway. Live, `/api/v1/operational-picture` returns **419 aircraft tracks
and four hardcoded empties**.

Two findings underneath it, both worse than the gap:

- **`api-002`'s justification expired without anyone noticing.** It records those empties as
  warranted "because no detector, RF source or generator exists". The *principle* stands; the
  *condition* is false — eight rules, the RF source, the generator, 103 stored bundles, 155 stored
  hypothesis rows. Nothing checks whether a recorded reason is still true.
- **A producer-less field.** `op-003` consumes `detectionSummary`, `op-006` consumes
  `timelineEvents`, `api-007` filters both — and **no item produced them**. Invisible by
  construction: every consumer can be built and pass while the field stays empty forever.

Two items were written rather than the gap patched:

| Item | What it owns |
|---|---|
| **`anom-015`** | The detection pass over one completed run. The composition of the eight rules exists **only** inside `measurements/corpus/detection_metrics.py`, outside lint, mypy, the suite and the coverage gate — so the ordering behind every detection figure is the one part nothing checks, while all eight rules sit at 100% individually. Same shape as `ai-004`'s payload defect. Its own stage (never in generation, never on read); records the policy that produced the findings, which **needs a migration**; refuses a run with no completion stamp. |
| **`api-012`** | The picture carries detection. Its sharpest constraint: **a run with no detection pass must not produce the same payload as a run the pass found nothing in** — `anom-008`'s argument at the API boundary. |

## Files in flight

Tree is clean. Nothing half-finished.

## Changed

| Commit | What |
|---|---|
| `a310896` | `spec: amend api-011 — the lease, the refusal channel, and the clock` |
| `299c6bf` | `test: add tests for api-011` |
| `80ace99` | `feat(api-011): one batch at a time - tests pass` |
| `fe1eca3` | `test(api-011): mutation pass, 17 of 17` |
| `b1e6bb3` | `docs: api-011 write-up` |
| `b7c8efe` | `docs: record api-011's manual verification` |
| `ab22843` | `spec: amend eval-001, add anom-015 and api-012` |
| `7ca1968` | `feat(eval-001): the batch runner's reproducibility, proved - tests pass` |

New files: `backend/app/scenario/guard.py`, `backend/tests/test_eval_batch_runner.py`,
`backend/measurements/mutation/mutate_api011_guard.py` + `.log`,
`backend/measurements/corpus/batch_reproducibility.py` + `.log`.

Backend edited: `app/api/v1/scenario.py`, `app/api/v1/schemas/scenario.py`, `app/scenario/batch.py`,
`tests/test_api_scenario.py` (+26), `tests/test_scn_control_contract.py` (+2), `tests/conftest.py`
(the guard ceiling), `tests/test_ops_database_guard.py` (+1).

Frontend edited: `types/scenarioControl.ts`, `lib/api.ts`, `hooks/useScenarioControl.ts`, `App.tsx`,
`screens/scenarioControl.tsx`, `test/scenarioAccess.test.tsx` (+5), `test/navigation.test.tsx`.

Docs: `docs/spec.jsonl` (`api-011` amended and passing, `eval-001` amended and passing, `api-002`
amended, `anom-015` and `api-012` added), `docs/qa.md` (§124-132 + 8 glossary rows),
`docs/thesis_notes.md` (12 subsections, now 248), `docs/implementation.md`,
`backend/measurements/README.md`, `CLAUDE.md`.

No new dependencies. No new requirements. The progress note was **not** touched: neither item changes
the story it tells, and nothing on it went stale. `anom-015`/`api-012` will change that when built.

## Failed attempts

- **`api-011`'s own scope line was wrong, and reading the code before writing tests is what caught
  it.** It said "one sentence of screen copy"; there was nowhere to put a sentence. Six findings went
  into the amendment before a test was written, and that one changed the scope.
- **The item said the launcher releases the guard in a `finally`.** It cannot — `launch_batch` starts
  a thread and returns. Released there, the guard is free before a run row is opened.
- **A frontend test passed before the implementation existed.** It asserted no refusal is shown
  before anything is refused, vacuously true while nothing rendered a refusal. Only prove-red said
  so. Replaced with one requiring a refusal to appear and then clear.
- **`api-011`'s mutation pass found one survivor, and it was a limit on what a test can observe.** A
  check-then-set `take` survived the barrier test, because two threads released together are usually
  scheduled so one completes both halves first. A test that catches a defect *occasionally* is worse
  than none — it reads as coverage. Atomicity is now asserted against the parsed source.
- **The frontend suite had been passing and failing at the same time.** 86 green while the runner
  exited non-zero on an unhandled exception: `navigation.test.tsx` answered *every* path with the
  operational picture, so the scenario feed rendered it as a run list. Any CI gate over the frontend
  was broken regardless of the code. A defect in a test's fixture, which is the part nothing tests.
- **I was about to add an `app/` module to `eval-001` that it did not need.** The justification I
  reached for was the same one written into `anom-015` — that a composition producing a figure of
  record should not live only in an unchecked script — but that argument is about eight rules, not a
  three-line comparison. Caught before writing it. `eval-001` needed no production code.
- **`eval-001`'s first test asserted over the wrong population.** It expected the table to hold only
  the 20 runs it wrote; the shared `migrated_database` fixture seeds one run (id 8812) for the bundle
  suites, so there were 21. Reshaped to assert the *property* — nothing mismatches, exactly one batch
  re-derives — which is both robust to the fixture and the claim the item actually makes.
- **The test-database guard's ceiling was exactly one too low, and its comment is why nobody
  checked.** `MAX_FIXTURE_RUNS` was 20; a batch's floor is 20; plus the fixture's run that is 21. So a
  test writing one legitimate minimum batch refused the schema drop for **every database test after
  it in the session**, arriving as a fixture error in whatever ran next — the cause looks like the
  wrong test. The comment read "nothing legitimate sits in between, so these are set nowhere near
  either edge", and the value sat on the edge that sentence named. Raised to 40 (a corpus is 300), and
  the relationship to the batch bounds is now asserted rather than stated in prose.
- **The first `batch_reproducibility.py` grouped on the base seed alone** and reported a batch of
  twenty holding a hundred runs. A base seed behind 100 runs is **five batches of twenty**, one per
  scenario type — which is *why* the same twenty derived seeds appear five times, and is the mechanism
  behind every seed-matched comparison. Regrouped, and the seed-matching check came out of noticing it.
- **Two README rows were filed under the wrong heading** (`### The source-gap rule`), which is where
  recent rows have been accumulating regardless of topic. Refiled: the measurement into its own corpus
  subsection, the mutation harness into the mutation table with that table's three columns. The
  section's existing mixture was left alone — reorganising the file is not this item's work.
- **Workflow deviations, recorded.** `api-011`: two tests and one structural test added after first
  green, in response to the mutation pass. `eval-001`: **no red run was possible**, there being no
  production code; the substitute is a paired test that feeds the assertion a corrupted row and
  requires it to fail, stated in the test module's docstring rather than left implicit.

## Next step

1. **`eval-006`** — the blind-score ingest and inter-rater agreement. Still blocked until the second
   rater returns mid-October, and still the only thing between here and a complete evaluation chapter.
2. **`anom-015` then `api-012`** — now the sharpest gap in the project, and the two are ordered:
   nothing can be served until something runs. `anom-015` needs a migration (findings carry no policy
   column) and one **unmeasured figure**: the cost of a single detection pass, which decides whether
   the stage can be triggered when a batch completes or must stay a separate command. Measure before
   choosing, on `anom-014`'s and `scn-007`'s footing.
3. **The Hypotheses arc** — ten items, all unblocked, and it now reads differently: the *detection*
   layer is as invisible as the hypothesis layer, so `anom-015`/`api-012` and this arc are two halves
   of one problem — nothing this system computes can be seen in it.
   `ui-001` → `api-004` → `hyp-001` → `hyp-002` → `hyp-003` → `hyp-004` → `ai-010` → `api-005` →
   `fbk-001` → `fbk-002`, with **`api-009`** folded in along the way rather than as its own arc.
4. **A corpus with near-misses** would turn the detection table from a consistency result into an
   accuracy one. Out of scope, named in five places.

### Open and unowned

- **`CORPUS=v1` now selects nothing, and nothing refuses an empty population.** Measured: the store
  holds 380 runs, ids 21-400, every one carrying a base seed, so the predicate naming v1
  (`base_seed IS NULL`) matches zero rows — v1 did not survive the 2026-09-19 destruction. A script run
  under `CORPUS=v1` would measure no runs and print figures over nothing. Noted in
  `measurements/README.md` in place; retiring v1 outright is a decision rather than an edit.
- **A malformed response from `/scenario/runs` would white-screen the application** rather than
  degrade. The other screen's data source was not audited the same way.
- **Giving batch work its own Engine** is the complementary fix to `api-011`. Nothing sets
  `pool_size` or `max_overflow` either.
- **Reporting a batch that failed after acceptance.** `api-011` says a batch is running; nothing says
  one died.
- **`detection_findings` holds residue** — rows from whichever measurement touched whichever runs,
  with nothing recording which, and no column for the policy in force. Harmless while only tests read
  it (`findings_for_run` has no other caller); `anom-015` is where it is fixed.
- **Serialising enough for the campaign record to round-trip** (`ai-012`) — decided against, **trigger:
  do it first if a second campaign is ever run.** The one real exposure is closed by the committed
  per-call split.
- **`cost_is_complete` is vacuously true on an arm that made no calls** — recorded, not changed.
- Mutation harnesses for `pack.py`, `sampling.py`, `statistics.py`, `workbook.py` — 104 tests with
  nothing establishing they are load-bearing. The recent passes found eleven real gaps between them.
- Six measurement harnesses lack the guard-file-and-sentinel pattern; only the most recent check that
  a mutant parses and is not identical to the original.
- `measurements/README.md`'s section filing has drifted — recent rows land under
  `### The source-gap rule` regardless of topic.
- The 0.39 rate-excess singleton, seen once at n=40 and surviving to n=60 with no second example.
- 12 files not Black-formatted; `make format` touches them on every run.
- Nothing applies migrations to the application database in the ordinary path.
- `ai-011`'s harness has not been re-run since the corpus was regenerated.
- The credential loader is not generalised.
- `ai-008`'s superseded case has no corpus demonstration.
- `docs/phase9_hypothesis_layer.md` §8 still says N=1, which the twenty-bundle figures settle.
- Rebuilding evidence bundles corpus-wide would renumber the scored population (ids 247-308).
- The three progress-note charts still want a real visual pass.
- **The application database now holds 380 runs, ids 21-400.** The last 20 (`normal-baseline`, base
  seed 1284648146) came from `api-011`'s manual test and are excluded from every measurement *by
  construction* — `_corpus.run_filter()` pins corpus v2 to its three seeds by value.

### Two limitations from earlier sessions that must not be dropped

**The detection table measures wiring, not accuracy.** Every rate is 1.000 or 0.000. The radio side is
synthetic with the incident well above threshold by construction, the corpus holds no near-misses, and
one of three reportable types has no rule. The only figure carrying information from outside the
generator is the per-aircraft recall, 0.587 on two arms of three.

**The retry and fallback paths never fired.** Nothing was refused and nothing fell back on the scored
campaign, so a fallback rate of zero reports that the path was *not exercised* — not that it works.
