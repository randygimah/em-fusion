# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each time — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-14
**Branch:** `main`, clean. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session answered a prioritisation question — **not `api-011` next, but Phase 8** — then opened
Phase 8: three corrections to the backlog, a reasoning document for the whole phase, and the first
three items built. **`anom-002` (baseline), `anom-001` (`RF-NOISE`) and `anom-010` (`TRACK-GAP`)
all pass.** Between them they are the first code in the project that says what *normal* is, and a
rule for each side of the picture. The most important result of the session is not a rule but a
measurement: **the staged track signature is statistically indistinguishable from the corpus's own
background**, which forced `anom-010`'s output to be an intermediate finding and `anom-008` to be
rescoped.

## Current state

| | |
|---|---|
| Backend suite | **669 passed, 99.89%** via `make test-backend`, database tier live, ~145 s |
| Backend, local | 582 passed, 87 skipped, 95.94% (`make check` in `backend/`) |
| Frontend suite | **81 passed but the run exits non-zero** — see Failed attempts. Not green. |
| Spec items passing | **32 of 88** — `scn` 5/5, `adp` 7/8, `api` 5/11, `nav` 2/3, `db` 5/7, **`anom` 3/10** |
| New dependencies | None |
| Stack | **Up**, all three containers healthy |
| Runs in the database | **120** — 40 `aircraft-coverage-gap`, 20 each of the other four types, all completed |

### What exists now

**`anom-002` — the baseline engine.** `backend/app/detection/baseline.py`, a new `app/detection/`
package that is Phase 8's home. Mean, sample standard deviation and sample count **per
sensor-channel cell** over a trailing window, with an explicit insufficient-data result rather than
an average over one point. 27 tests, 100% on the module. It takes observations and returns values —
nothing in it reaches a database or a network, which is what lets the arithmetic be tested without
Docker.

Three design points that will matter to `anom-001` and after:

- **The caller names the quiet runs.** An observation carries no scenario type — `api-009` forbids
  it and `dal-001` gives the model nowhere to put one — so the engine cannot recognise staged data
  by inspection. It takes the set of permitted run ids and refuses anything else, all-or-nothing. A
  baseline computed from most of a batch is a wrong answer that looks like a right one.
- **The window is a trailing duration ending at the newest observation**, not at the wall clock. A
  replayed hour from 2022 has no relationship to the time now; a window anchored to `now` is empty.
  Evaluating the same observations at two ends is what makes the average roll.
- **Scope narrowed to RF metrics**, recorded on the item. The item also asks for track metrics per
  region; no region concept exists anywhere in the project and nothing consumes a track baseline.
  The engine is written per *cell*, so the track half is a second extractor plus a region decision
  rather than a rewrite. It needs its own spec item when something wants it.

**`anom-001` — the `RF-NOISE` threshold rule.** `backend/app/detection/rf_noise.py`, 28 tests, 100%
on the module, **fifteen mutations all caught**. Episodes of deviation per cell rather than one
anomaly per reading, since a run emits 5,040 readings. Four decisions carry forward:

- **The comparison has a direction per metric** — power upwards, SNR downwards. An absolute deviation
  reports a channel *quieter* than baseline as noise, which is a different fault and probably a dead
  receiver. **No run in the corpus would ever have exposed this**: staged interference only pushes
  the metric one way, so the wrong implementation and the right one agree on every run the generator
  can produce, and would have agreed throughout the scoring campaign.
- **Triggering readings are named by natural key** — sensor, channel, timestamp — not by a database
  id. `CanonicalObservation` has none by `dal-001`'s design, `scn-005`'s dense grid makes the three
  values unique, and the natural key is the form an analyst can actually check.
- **A cell with no usable baseline is reported unjudged, not skipped.** Otherwise `anom-008`'s
  zero-anomalies control is satisfiable by not having looked, and a detector with no baseline
  anywhere would post a perfect false-positive rate.
- **The affected area is a point**, and this is a gap recorded rather than solved: the `anomalies`
  table's `affected_area` is a **NOT NULL polygon**. The detector does not persist, so nothing is
  broken today, but whichever item first persists an anomaly inherits the question. An area needs
  corroboration from more than one sensor, which is `anom-004` and `anom-005`.

**`anom-010` — the `TRACK-GAP` continuity rule.** `backend/app/detection/track_gap.py`, 28 tests,
100% on the module, **seventeen mutations all caught**. The item as specced that morning was wrong,
and measuring before writing is what caught it — see Measurements below. What it became:

- **Two mechanisms**, because the two scenario types stage differently. `gnss-degradation` rewrites
  the reported position staleness and the rows keep arriving (`frozen_position`);
  `aircraft-coverage-gap` suppresses the rows, so the gap is the absence itself (`not_heard`). A rule
  with one mechanism is blind to one type. The shape travels on the finding because telling them
  apart is `anom-005`/`anom-006`'s whole job.
- **Frozen position requires fresh contact**, decided on measurement: it cuts the quiet-run
  background from 137.7 aircraft per run to 24.6 while leaving the staged margin at 3.4 — signal
  against background from about 1:40 to 1:7, at no cost.
- **Airborne and interior-to-box filters.** Without them four fifths of the findings are aircraft
  switched off on a stand or flying out of the box and back.
- **The `adp-008` exclusion list is deliberately not duplicated here.** Keeping known-bad tracks out
  of a run is the generator's job; a second copy is the trap this project already recorded once.
- **Output is an intermediate finding, not a reportable anomaly**, and `anom-008` was amended
  alongside to count only the fused reportable types. It also gained two obligations rather than
  losing any: the intermediate-finding rate on quiet runs is recorded, and a detector reporting
  *zero* intermediate findings on a quiet run now fails, because the corpus is known to contain them.

**Three backlog corrections**, all committed before any code:

- **`anom-010` is new, because FR-304 had no spec item.** Nine `anom-*` items covered eight of the
  nine detection requirements. `anom-004` clusters track-continuity anomalies and `anom-006`
  consumes track dropout clusters, and nothing produced one — the rule the fusion pair rests on was
  the one rule nobody had written down. **Search trap worth remembering:** grepping `FR-304` returns
  a hit that is `NFR-304` in an unrelated item.
- **`db-004` is pulled forward from Phase 6**, where it is the last unticked item. `anom-004`,
  `anom-005` and `anom-007` all name it, and there are no discontinuities to query over until
  `anom-010` produces them. Phase 6 now cross-references where it is actually built.
- **Phase 8 has an ordering note**, because the identifiers mislead: `anom-001` consumes the
  baseline `anom-002` produces. Second time this has happened — Phase 7 carries the same note for
  `scn-001` and `scn-005`.

**`docs/phase8_detection.md` is new** — 369 lines, fourteen sections, added to the repo map. What
the detection layer is, the four reasons it is deterministic only, the chain from observations to
bundles, the five rules and the discrimination between them, correct non-detection as a control, the
corpus-dropout problem, and what the phase deliberately does not do. Written as drafting material to
proof-read `thesis_notes.md` and the progress note against.

### Measurements taken this session

**The quiet baseline data, against the twenty completed `normal-baseline` runs:**

| | |
|---|---|
| RF readings | 100,800 |
| Sensor × channel cells | 56 (7 × 8) |
| Samples per cell | 1,800 |
| Pooled mean / sd, power | −95.00 dBm / 1.50 dB |
| **Spread of per-cell means** | **0.177 dB** (−95.081 to −94.904) |
| **Range of per-cell sds** | **1.437 to 1.551 dB** |

The last two rows are the load-bearing ones. **The 56 cells are statistically indistinguishable on
quiet data**, because `scn-001`'s emitter gives every cell the same nominal by construction. So a
pooled per-sensor baseline would reproduce the per-cell numbers almost exactly, and *any test of the
per-channel requirement built from quiet runs could not fail*. The granularity tests are built from
a constructed series with one channel 15 dB loud, and assert that no cell's baseline equals the
per-sensor pool. Found by measuring before writing, which is the first time that ordering has held
in this project rather than a mutation pass catching it afterwards.

**Mutation results, `anom-002`:** 11 applied, **10 of 10 killable caught**, 1 equivalent mutant.

| Mutation | Result |
|---|---|
| Pool the channels into one per-sensor baseline | caught (5 tests) |
| Accept observations from any run | caught (2) |
| Accept a track observation | caught (1) |
| Allow a minimum of one sample | caught (1) |
| Return a mean for a thin cell | caught (4) |
| Ignore the window | caught (3) |
| Anchor the window to the wall clock | caught (19) |
| Population instead of sample standard deviation | caught (1) |
| Never report a baseline as degenerate | caught (1) |
| Accept an empty set of baseline runs | **survived, then fixed** — see Failed attempts |
| `statistics.mean` → `sum(values) / len(values)` | **equivalent mutant**, see below |

**The equivalent mutant is worth carrying forward.** Replacing `statistics.mean` with plain
division changes no result, because **CPython has used Neumaier compensated summation for floats
since 3.12**. Verified rather than assumed: a search over 300,000 randomly generated 30-sample sets
of plausible dBm readings found none whose float sum differs when reversed, and `sum([0.1] * 10)`
returns exactly `1.0` on both interpreters in use (3.14 locally, 3.13 in the container). So the
honest score is ten of ten killable caught with one equivalent mutant identified — **a mutation
score that does not separate equivalent mutants is not a measurement of test quality**, and this is
a concrete instance to cite.

## Files in flight

Nothing half-built; the tree is clean.

## Changed

Seven commits, `6befa27` through `8746cb5`: three spec commits, one phase document, one test commit,
one implementation, two docs passes.

Added: `backend/app/detection/__init__.py`, `backend/app/detection/baseline.py`,
`backend/tests/test_anom_baseline.py`, `docs/phase8_detection.md`.
Modified: `docs/spec.jsonl` (`anom-010` added; `anom-002` amended twice then set passing),
`docs/implementation.md` (Phase 8 ordering note, two new checklist items, the baseline item ticked,
the Phase 6 `db-004` cross-reference), `docs/thesis_notes.md` (three subsections),
`docs/qa.md` (entries 60 and 61, three glossary terms), `CLAUDE.md` (repo map).

**The progress note is at version 19**, republished twice this session. Baseline turned
solid and Anomaly detection went to *First rule*; the missing-middle framing was rewritten; the
headline figures were corrected (584 → 641 tests, 99.93% → 99.89%, 29/86 → 31/88 capabilities); and a
new section was added — *What normal looks like, and noticing when it is not* — carrying the
fifty-six-cell measurement, the finding that quiet data cannot prove the requirement it was measured
for, a hand-authored figure of the episode rule, and the wrong-implementation panel. Two claims that
had become false were fixed: *nothing is detected*, and the reason nothing has ever been marked.
Version 19 then added the aircraft-side rule and the detection-versus-attribution finding, with the
staged-versus-quiet table, a scatter figure contrasting scattered background gaps against a staged
cluster, the four-fifths filter table, and the independent validation of the August exclusion list.
It also corrected two sentences version 18 had published that morning and that `anom-010` made false
within hours — both claiming the aircraft side had no rule.

## Failed attempts

- **The frontend suite is not green, and the last two handoffs said it was.** `pnpm test` reports
  *81 passed* and then exits non-zero on an unhandled error:
  `TypeError: control.runs.map is not a function` at `scenarioControl.tsx:344`, thrown from
  `navigation.test.tsx` during *"stops polling the picture when the analyst leaves it"*. **Two
  defects, both pre-existing from `api-010` and neither caused by this session's work.** First, that
  test stubs `fetch` with a single mock resolving `json: async () => operationalPicture` for *every*
  path, so when Scenario Control mounts, its runs poll is answered with the picture payload — the
  test filters calls by path for its assertion but the stub does not discriminate. Second, and the
  one that matters beyond the test: **`useScenarioControl` does not check that the response is an
  array.** `api-010`'s posture is that a failed poll keeps the rows and changes only the indicator,
  but that covers a *rejected* request, not a 200 carrying the wrong shape — which is what a proxy
  returning an error page, or a contract change, actually looks like. The screen crashes rather than
  degrading. The error surfaces after the assertion, so the test still passes and the count still
  reads 81; **reading the count rather than the exit status is what hid it.**
- **Four mutation survivors on `anom-010`, of four different kinds, and only two were test gaps.**
  Two were boundary cases — both thresholds compare strictly and nothing sat exactly on the boundary,
  99 s and 150 s bracketing it without touching it. `anom-001` has that test because its spec item
  names the boundary; `anom-010`'s did not, so it was not written. **A test propagates between rules
  by being in the spec item, not by being a good idea.** One was a test passing for the wrong reason
  and the **second instance of one exact shape**: deleting the non-positive-threshold guard left
  everything green because the *other* policy guard raised instead, any positive contact window being
  longer than a zero threshold. Same as `anom-002`'s empty-run-set test; same fix, assert on the
  message. General form: **a guard reachable only through the guard beside it is not under test**, and
  validation guards cluster. The fourth was **not a test gap at all — I built the mutation wrongly**:
  `zip(reports, reports[1:] or reports)` differs from the original only for a single-report aircraft,
  where it pairs a report with itself and yields a zero interval. An equivalent mutant reported as a
  survivor. Rebuilt properly it killed 23 of 28 tests. **Mutation testing has its own failure mode**,
  and both equivalent mutants this project has seen were mine rather than inherent.
- **A coverage line found a behaviour I had not thought of.** Nothing tested an aircraft whose
  position *recovers* and is lost again — the frozen-position twin of `anom-001`'s episode split,
  which I had written for RF and not carried across. Two events, not one.
- **A docs commit claimed more than it contained.** A patch script hit a failed assertion partway
  through, having already written two of three files, and the commit ran anyway. `0bae703` overstates
  itself; the checklist tick is in the follow-up commit. **Check the exit status of a multi-step edit
  before committing it.**
- **A determinism test with one cell could not catch an ordering bug across cells.** `anom-001`'s
  fourteen-of-fifteen mutation was the one replacing sorted iteration over cells with arrival order.
  The test asserting that traversal order is not an input did not catch it, because it was written
  with a single cell — and with one cell there is no cell ordering to get wrong. Fixed with two cells
  and an explicit assertion on the emitted order. **Third instance of one shape**, now stated as a
  rule in `thesis_notes.md`: a test that distinguishes two behaviours must contain the structure
  along which they differ. Common values cannot separate them (`api-010`), one sample cannot exercise
  an ordering (`anom-001`), uniform data cannot demonstrate a requirement about non-uniformity
  (`anom-002`).
- **A test passed for the wrong reason, and mutation found it.** Deleting the guard that refuses an
  empty set of baseline runs left every test green: with observations supplied, an empty allowed-set
  means every observation belongs to no listed run, so the *next* guard raises and the test still
  sees its exception. Rewritten to call with no observations at all — where nothing but the deleted
  guard can raise — and to assert on the message text rather than the exception type. Same family as
  the two `api-010` tests that could not fail: **a test must be reachable only through the thing it
  claims to test.**
- **Two of the 27 tests were written after the implementation**, not before — a non-positive window
  guard and the empty-input path, both surfaced by the coverage report rather than by the test-first
  pass. Sound tests, wrong sequence. A workflow deviation, recorded in `thesis_notes.md`. Same thing
  happened to `api-006`'s launcher.
- **I connected to the database as the wrong user.** `psql -U em_fusion` fails with
  `role "em_fusion" does not exist`. Compose sets `POSTGRES_USER` to **`postgres`** with
  `POSTGRES_DB: em_fusion` — the database is named for the project, the role is not.

## Next step

1. **`db-004`** — the PostGIS spatial query, now that `anom-010` produces discontinuities to query
   over. It is the last unticked Phase 6 item and `anom-004`, `anom-005` and `anom-007` all name it.
2. **`anom-004`** — spatial clustering, immediately after. **This is where the session's central
   finding gets tested**: the discriminating information is spatial, so clustering is what has to
   turn 138 scattered findings per quiet run into nothing reportable. The open risk is whether those
   138 ever cluster by chance near a busy airport, which `anom-006` would then fire on. Measure it
   rather than pre-tune a radius against an imagined problem.
3. **The frontend suite exiting non-zero** is the first owed item below and is now the oldest lie in
   the handoff. Small.
4. **`anom-003`** — the z-score detector, which shares `anom-001`'s shape and is the smallest of the
   remaining detectors.

Owed, with an owner but no date:

- **`useScenarioControl` crashes on a 200 with the wrong shape**, and the navigation test's fetch
  stub answers every path with the picture payload. Both above. The product half needs a spec item:
  the honest behaviour is to treat a malformed success exactly like a failed poll.
- **A failed batch cannot reach the screen.** The response is sent before the work starts, so a
  batch that dies looks exactly like one still running. Needs a spec item; the open question is
  where the failure lives — a run row, a status endpoint, or in-memory state.
- **`api-011` is specced and agreed but unbuilt** — refuse a second batch while one is in flight.
  Deferred deliberately this session: `make generate` does not go through the API, so campaign
  generation cannot hit the pool exhaustion. Do it first if a demo of the screen is imminent.
- **The configuration form offers dials that are inert for the selected type**, with nothing saying
  so: zone radius does nothing for `rf-sensor-fault`, and noise elevation and spectral extent do
  nothing for `aircraft-coverage-gap`.
- **The runs table shows the 50 most recent, unfiltered and unpaged**, against 120 rows and a
  campaign of 150.
- **The `adp-008` exclusion list is not applied to baseline windows**, and this is now measured
  rather than suspected: 23 interior airborne gaps across the 20 quiet runs, from 4 aircraft, all 4
  on the list. `load_exclusions` already exists in `app/scenario/tracks.py`; the generator does not
  pass it for baseline windows. Owed to the generator, not to the detector.
- **The GNSS-degradation scenario is not detectable from the track stream alone.** Measured, and
  recorded as a limitation: any reported detection of it depends on the RF side agreeing, and
  `eval-002` should say so rather than presenting a combined figure as though the track rule
  contributed independently.
- **`anom-008` now has a threat to validity to report**, written on the item: scoping the
  false-positive rate to the fused layer means a reader could mistake it for a statement about
  detection as a whole. Both numbers get reported.
- **Track-metric baselines have no item.** `anom-002` was narrowed to RF; the track half needs a
  region definition and a consumer before it is worth writing.
- **Detection latency still has no precise definition**, and the Track 0 item says to fix it
  *before* any measurement code exists. Gates `anom-009` only.
- **Detector radii for `anom-005` and `anom-007`** from the measured band [55.7, 85.7) km.
- **`docs/qa.md` has two entries numbered 47** — line 3154 and line 3245. Pre-existing, and **not**
  to be fixed by renumbering, which the project's own rule forbids; the fix is a note on the second
  saying which is which.
- **Decide whether the five batches share one base seed.** Recommended and measured; belongs to
  `eval-001` with whether the incident dials vary within a batch. Both must be settled before the
  scoring campaign is generated.
- **Decide on frontend coverage tooling** (`@vitest/coverage-v8`). Argued for by seven findings now.
- **`nav-002`, the system-health strip, inherits a question from `nav-003`**: what it shows at 56px.
  It must not be answered by letting a collapse hide health.
- **Reset needs an item** once a batch can be cancelled, and **replay is unreachable through
  `start`**, which takes a batch of 20–30.
- **Run `pnpm format` across the frontend** as its own `style:` commit, or drop the formatter config.
- **A run row cannot distinguish a run still going from one that died.** A status column would fix it.
- **`op-001`'s badge must key off the run, not off an observation's data mode.**
- **A floor on the affected-aircraft count** rather than a bare 8%, once detectors exist.
- **Confirm the digest survives an x86-64 run.** The first CI job produces this for free.
- **The frozen-position shortcut is a limitation, not a bug.**
- **Adopt TanStack Query at the Phase 3 view filter, not before.**
- **`scenario.health` renders as a bare `unknown`**; left for `op-001`.
- **The parity test compares field names, not types.**
- **`app/corpus/build.py` resolves `.env` from the repository root.**

Open and unowned:

- **Root `make check` has still not been run in full.**
- **mypy does not check `tests/`.**
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence remain open.
