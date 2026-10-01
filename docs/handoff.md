# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

Three items closed this session, and one question reframed the roadmap.

1. **`api-011`, one batch at a time** — a defect fix. Several starts in quick succession left the
   backend serving nothing at all.
2. **`eval-001`, the batch runner** — closed on a **measurement rather than code**.
3. **The question:** *does detector output on injected anomalies show in the app at all?* No. Two
   items were written in response, and the first is now built.
4. **`anom-015`, the detection pass** — the composition of the eight rules moves out of a
   measurement script and into the application.

## Current state

Backlog **71 of 106**. Tree clean.

- Backend: **1,781 passed at 99.92%** in containers. `make lint` and mypy clean.
- Frontend: **86 passed across 8 files, exit 0** (it exited non-zero before `api-011`).
- `app/detection/chain.py` — new, 102 statements, **100%**, 24 tests.
- `app/scenario/guard.py` — new, 39 statements, **100%**.
- Mutation: **17 of 17** (`api-011`), **19 of 20 with one proven equivalent** (`anom-015`).
- New measurements of record: `batch_reproducibility.log`, `mutate_anom015_chain.log`.
- **The detection figures were re-measured and are byte-identical.** The one line that moved is the
  provenance stamp: **`c421c41506fd` → `79ef76db46ba`**, because the record gained the sixty quiet
  runs normality was measured over. `docs/qa.md` and `docs/progress_note.html` are corrected.

### `anom-015` — the detection pass

**Why it existed to be built.** Each of the eight rules had its own suite at 100%. The *ordering*
lived in one place only — `measurements/corpus/detection_metrics.py` — which sits outside ruff, mypy,
pytest and the coverage gate. So the composition behind every detection figure the project quotes was
the one part nothing checked. `ai-011` exists because five separately working parts admitted three
ways of being joined, two of which run perfectly and report something false; detection had no
equivalent.

**Validated by reproduction.** The script was re-pointed at the new composition and re-run over the
same 300 runs. Forty-three lines of output, **one** differed — the stamp. Every figure identical.

**Measured, as the item required before choosing a trigger:**

| | |
|---|---|
| One run | 1.04–1.29 s, median **1.22 s** |
| …of which reading observations | ~1.0 s. The rules are 0.11–0.23 s |
| Normality, once per session | 11.2 s over 60 quiet runs |
| A 20-run batch | **~35 s** against the batch's own ~105 s |

So the stage **can** fire when a batch completes. It still cannot run per request — the baseline, not
the pass, is the reason.

**Three design corrections the suite forced.** Each is a line worth keeping:

- **It reads its own observations.** Taking them as parameters made `assess(run 7, observations of run
  9)` representable, and the citation check that catches it runs *after* run 7's findings are written
  from run 9's data — a partial wrong write, not a loud refusal. "The failure is loud so the risk is
  low" only holds when the failure is loud *before* the damage.
- **Each claim keeps the receivers its evidence rested on.** No claim carries them, and `anom-009`'s
  registry states a count of receivers rather than a formula because `anom-005`'s window is the union
  of its receivers'. The pass is the only place both halves are in view.
- **It builds but does not store the bundles.** Findings are derived, replaced per run per rule and
  cited by nothing; `eval-004`'s pre-registered sample names its twenty bundles **by id**, so a pass
  rebuilding them corpus-wide would renumber that population and stop the draw reproducing itself. A
  row whose identity something else cites is not one a derived-data stage may replace on its own
  initiative.

`0008` adds a **nullable** policy column: null means *written before this item*, which is true, where
`NOT NULL` would need a server default inventing provenance or deleting the residue rows.

### The gap that remains

**`api-012` is unbuilt, so nothing the detection layer produces is on screen yet.** Live,
`/api/v1/operational-picture` still returns aircraft tracks and four hardcoded empties. `api-002`'s
justification for them — *"because no detector, RF source or generator exists"* — expired without
anyone noticing, and three items consume those fields while none produced them.

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
| `c53943d` | `docs: eval-001 write-up, and the gap the app question found` |
| `3e68427` | `spec: amend anom-015 — the baseline is an input, and two readers invent fields` |
| `a907814` | `test: add tests for anom-015` |
| `ffcfe43` | `feat(anom-015): the detection pass, in the application - tests pass` |
| `19dd7b7` | `test(anom-015): mutation pass, 19 of 20 with one proven equivalent` |

New files: `app/scenario/guard.py`, `app/detection/chain.py`,
`alembic/versions/0008_detection_finding_policy.py`, `tests/test_eval_batch_runner.py`,
`tests/test_anom_chain.py`, `measurements/mutation/mutate_api011_guard.py` + `.log`,
`measurements/mutation/mutate_anom015_chain.py` + `.log`,
`measurements/corpus/batch_reproducibility.py` + `.log`.

Backend edited: `app/api/v1/scenario.py`, `app/api/v1/schemas/scenario.py`, `app/scenario/batch.py`,
`app/db/findings.py` (the policy on every row), `app/db/repository.py` (`observations_for_run`),
`measurements/corpus/detection_metrics.py` (re-pointed at the chain) + `.log` and its six exports,
`tests/conftest.py` (the guard ceiling), plus five test modules.

Frontend edited: `types/scenarioControl.ts`, `lib/api.ts`, `hooks/useScenarioControl.ts`, `App.tsx`,
`screens/scenarioControl.tsx`, `test/scenarioAccess.test.tsx`, `test/navigation.test.tsx`.

Docs: `docs/spec.jsonl` (`api-011`, `eval-001`, `anom-015` amended and passing; `api-002` amended;
`anom-015` and `api-012` added), `docs/qa.md` (§124-137 + 16 glossary rows), `docs/thesis_notes.md`
(17 subsections, now 253), `docs/implementation.md`, `docs/progress_note.html` (the stamp only),
`backend/measurements/README.md`, `CLAUDE.md`.

No new dependencies. No new requirements. The progress note was otherwise **not** rewritten: nothing
this session changes the story it tells. `api-012` will.

## Failed attempts

- **`api-011`'s scope line was wrong**, and reading the code before writing tests caught it. It said
  "one sentence of screen copy"; there was nowhere to put a sentence, because the seam dropped the
  feed's refusal and every 422 the backend ever returned was invisible.
- **The item said the launcher releases the guard in a `finally`.** It cannot — `launch_batch` starts a
  thread and returns, so releasing there frees the guard before a run row is opened.
- **A frontend test passed before its implementation**, asserting no refusal is shown before anything
  is refused — vacuously true while nothing rendered a refusal. Only prove-red said so.
- **`api-011`'s mutation pass found a limit on what a test can observe.** A check-then-set `take`
  survived the barrier test: two threads released together are usually scheduled so one completes both
  halves first. A test that catches a defect *occasionally* reads as coverage, so atomicity is now
  asserted against the parsed source.
- **The frontend suite had been passing and failing at the same time** — 86 green while the runner
  exited non-zero on an unhandled exception, so any CI gate over it was broken regardless of the code.
  A defect in a test's fixture, which is the part nothing tests.
- **I was about to add an `app/` module `eval-001` did not need**, reaching for the argument written
  into `anom-015` — which is about eight rules, not a three-line comparison. Caught before writing.
- **`eval-001`'s first test asserted over the wrong population**, expecting only the 20 runs it wrote;
  the shared fixture seeds one more. Reshaped to assert the property rather than the count.
- **The test-database guard's ceiling was exactly one too low, and its comment is why nobody checked.**
  20 runs, against a batch floor of 20 plus the fixture's run. The comment read "set nowhere near
  either edge" and the value sat on the edge that sentence named. Raised to 40, relationship asserted.
- **`batch_reproducibility.py` first grouped on the base seed alone** and reported a batch of twenty
  holding a hundred runs. A base seed behind 100 runs is **five** batches of twenty, one per scenario
  type — which is *why* twenty derived seeds appear five times, and is the mechanism behind every
  seed-matched comparison. The seed-matching check came out of noticing it.
- **`anom-015`'s first design took observations as parameters.** Rejected by a `ResolutionError` the
  suite produced, and the reason generalises — see Current state.
- **`anom-015`'s central test was worthless and the mutation pass proved it.** It asserted the
  aircraft findings are written before the rules that query them, by watching the statements the
  engine issued — and removing that write left it green, because the *radio* write still preceded the
  query. The assertion named a table where the claim names a rule.
- **Five further survivors were one cause: every test produced a single claim with nothing
  suppressed.** On such a run, counting bids instead of reported claims, counting claims instead of
  claims-of-this-type, keeping a zone's first receiver and dropping the declined zones all give
  identical answers. **Second time this has happened** — `anom-009` recorded the same shape — so it is
  now a standing caution: a suite is weakest exactly where its fixtures are simplest.
- **I wrote a mutation result into the README before the pass had finished.** Caught and replaced with
  a placeholder, then filled from the log. A predicted figure in a document of record is the thing
  this project's whole measurement discipline exists to prevent.
- **`make migrate` had to be run by hand** before the re-measurement, because nothing applies
  migrations to the application database in the ordinary path. The standing open item, biting.
- **Workflow deviations, recorded.** `api-011`: three tests added after first green from the mutation
  pass. `eval-001`: **no red run was possible**, there being no production code — the substitute is a
  paired test that feeds the assertion a corrupted row and requires it to fail, stated in the test
  module's docstring. `anom-015`: six tests added after first green, from the mutation pass.

## Next step

1. **`api-012`** — the operational picture carries detection. Now the shortest path to something
   visible: `anom-015` produces the findings and nothing serves them. Its sharpest constraint is
   already written: **a run with no detection pass must not produce the same payload as a run the pass
   found nothing in** — `anom-008`'s argument at the API boundary. Needs a repository read over stored
   findings, and `findings_for_run` has had no caller outside tests until now.
2. **`eval-006`** — the blind-score ingest. Still blocked until the second rater returns mid-October,
   and still the only thing between here and a complete evaluation chapter.
3. **The Hypotheses arc** — ten items, all unblocked. `ui-001` → `api-004` → `hyp-001` → `hyp-002` →
   `hyp-003` → `hyp-004` → `ai-010` → `api-005` → `fbk-001` → `fbk-002`, with **`api-009`** folded in
   along the way. With `api-012` this is the other half of one problem: nothing this system computes
   can be seen in it.
4. **A corpus with near-misses** would turn the detection table from a consistency result into an
   accuracy one. Out of scope, named in five places.

### Open and unowned

- **Who triggers the detection pass.** `anom-015` is built and nothing calls it outside the
  measurement script and the suite. Measured at ~35 s for a twenty-run batch, so chaining it to a
  completed batch is affordable — but that is a decision, and the pass deliberately does not make it.
- **`CORPUS=v1` selects nothing, and nothing refuses an empty population.** Every run in the store
  carries a base seed, so v1's predicate matches zero rows. A script run under it would print figures
  over no runs. Noted in `measurements/README.md`; retiring v1 is a decision rather than an edit.
- **The `anomalies` table is dead** — created by `0001`, never written to by anything. `evb-001`'s
  one-bundle-per-claim is the claims' persisted form. Retiring it is a migration nobody has taken.
- **A malformed response from `/scenario/runs` would white-screen the application** rather than
  degrade. The other screen's data source was not audited the same way.
- **Giving batch work its own Engine** is the complementary fix to `api-011`. Nothing sets
  `pool_size` or `max_overflow` either.
- **Reporting a batch that failed after acceptance.** `api-011` says a batch is running; nothing says
  one died.
- **Nothing applies migrations to the application database in the ordinary path** — this session had
  to run `make migrate` by hand mid-measurement.
- **Serialising enough for the campaign record to round-trip** (`ai-012`) — decided against, **trigger:
  do it first if a second campaign is ever run.**
- **`cost_is_complete` is vacuously true on an arm that made no calls** — recorded, not changed.
- Mutation harnesses for `pack.py`, `sampling.py`, `statistics.py`, `workbook.py` — 104 tests with
  nothing establishing they are load-bearing. The four recent passes found seventeen real gaps.
- Six measurement harnesses lack the guard-file-and-sentinel pattern.
- `measurements/README.md`'s section filing has drifted; recent rows landed under
  `### The source-gap rule` regardless of topic until this session refiled two.
- The 0.39 rate-excess singleton, seen once at n=40 and surviving to n=60 with no second example.
- 12 files not Black-formatted; `make format` touches them on every run.
- `ai-011`'s harness has not been re-run since the corpus was regenerated.
- The credential loader is not generalised.
- `ai-008`'s superseded case has no corpus demonstration.
- `docs/phase9_hypothesis_layer.md` §8 still says N=1, which the twenty-bundle figures settle.
- Rebuilding evidence bundles corpus-wide would renumber the scored population (ids 247-308) — now
  **enforced** rather than only recorded, since `anom-015` refuses to store bundles itself.
- The three progress-note charts still want a real visual pass.
- **The application database holds 380 runs, ids 21-400.** The last 20 came from `api-011`'s manual
  test and are excluded from every measurement by the corpus seed pin.

### Two limitations from earlier sessions that must not be dropped

**The detection table measures wiring, not accuracy.** Every rate is 1.000 or 0.000. The radio side is
synthetic with the incident well above threshold by construction, the corpus holds no near-misses, and
one of three reportable types has no rule. The only figure carrying information from outside the
generator is the per-aircraft recall, 0.587 on two arms of three.

**The retry and fallback paths never fired.** Nothing was refused and nothing fell back on the scored
campaign, so a fallback rate of zero reports that the path was *not exercised* — not that it works.
