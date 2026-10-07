# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session ran 6–7 October 2026. It took the scope agreed at the start — **`anom-017` and the
`op-010` collapse amendment, leaving the panel chain for its own session** — and both landed. It
also trimmed `CLAUDE.md` below the 150k-character limit, corrected a misreading of what the
detection metrics measure (and put the correction in the progress note), and dropped the
branch/worktree workflow: **work is now committed directly on `main`**.

## Current state

Backlog **85 of 117** (83 at the start). `anom-017` and `op-010` are `passes: true`. Tree clean,
`main` in sync with `origin/main` at `3e96140` plus this handoff's commit.

- Backend: **2067 passed, 99% coverage** (5541 statements, 4 missed), ruff, Black and mypy clean.
- Frontend: **250 passed** (236 at the start), Biome and `tsc -b` clean.
- Mutation: `mutate_op010_collapse.log`, **14 of 14 killed**. No mutation pass was run over
  `anom-017` — see Next step.

### The store, after `anom-017`

| | Before | After |
|---|---|---|
| Completed runs | 460 (21–480) | 460 |
| Stamped at the 100-quiet-run baseline | 80 | **440** |
| Stamped at the 60-quiet-run baseline | 380 | **20** — the cited runs, by design |
| Evidence bundles | 151 | **297** |
| Runs with a claim and no bundle | 140 | **0** |
| Hypotheses | 155 | 155 |
| Detection findings | 9454 | 9460 |

Runs 421–480 were **generated from Scenario Control on 6 October**, not by any script; the handoff
before this one described a 400-run store. The pre-re-score dump is
`pre_anom017.dump` in this session's scratchpad (sha256 `556aa4e0…`, four tables) — scratchpad is
session-local, so treat it as gone.

### What `anom-017` measured

- **Re-score** (`rescore_baseline.log`): 440 of 460 re-scored in 11.1 min, 20 refused by `db-011`
  and checked unmoved, 0 failures. **11 runs' claims moved, all window boundaries by 10–30 s; no
  claim appeared or disappeared** (90 interference, 186 fault, before and after). Moved: 71, 135,
  204, 224, 264, 310, 319, 330, 339, 370, 379 — ten of them inside the 300-run corpus.
- **Results table** (`detection_metrics.log`): **every figure byte-identical** to the 60-run figures
  of record. Only the provenance moved: `BASELINE.quiet_run_count` 60→100, date, digest
  `79ef76db46ba` → `d2a2c04ab428`. Store checksums before and after the run identical. The
  handoff's prediction that latency would move was **wrong**: medians 10/20/10 s, range 10–90 s,
  unchanged.

### What changed in behaviour

- `BASELINE_QUIET_RUNS` in `app/detection/settings.py`: 100 `PinnedRun(run_id, seed)`, five batches of
  twenty. `measure_normality` refuses — naming every run — if any is absent, unfinished, not
  `normal-baseline`, or carries another seed. **Consequence: on a freshly generated database, batches
  started from the screen are not scored** until the constant is re-derived for that corpus.
- `score_batch` takes `quiet_runs` (default the constant) and no longer calls `quiet_run_ids`.
- `assess_without_storing`: the pass inside an always-rolled-back transaction; the only path that
  skips the bundle write. `detection_metrics.py` uses it and **no longer writes to the store**.
- The evidence panel collapses; its header always carries the hour's summary
  (*"3 conclusions · 1 with no stored evidence"*, *no conclusions*, *loading*, *could not be loaded*,
  *not examined*). Preference in `localStorage` key `em-fusion:evidence-collapsed`.

## Files in flight

None. The tree is clean.

## Changed

| Commit | Message |
|---|---|
| `469c4d7` | `docs: trim CLAUDE.md repo map to pointers` (154k → 37k chars) |
| `13aeff4` | `docs: detection metrics grade the rules, not AI vs rules` |
| `ee835e2` | `spec: amend anom-017 -- cited runs refused, seeds pinned, refusal in measure_normality` |
| `856a41c` | `test: add tests for anom-017` |
| `a45c128` | `spec: amend anom-017 -- a measurement writes nothing` |
| `28e624c` | `test: add tests for anom-017 -- a measurement writes nothing` |
| `afd3f8f` | `feat(anom-017): pin the baseline's quiet runs with their seeds - tests pass` |
| `8b9ab8c` | `measure: re-score under the pinned baseline, re-run the results table` |
| `2ef3f2c` | `docs: anom-017 -- measurements README, repo map, thesis notes` |
| `8c974de` | `merge: anom-017 …` |
| `3e6bb3e` | `test: add tests for op-010 -- the panel collapses and its header still counts` |
| `21bc041` | `feat(op-010): the evidence panel collapses and its header still counts - tests pass` |
| `a7c40fd` | `measure: mutation pass over op-010's collapse -- 14 of 14` |
| `1f8c1e7` | `docs: op-010 -- repo map` |
| `3e96140` | `merge: op-010 …` |

**New, backend** — `tests/test_anom_baseline_pin.py` (19), `tests/test_anom_measure_without_storing.py`
(8), `measurements/corpus/rescore_baseline.py` + `.log`, `measurements/mutation/mutate_op010_collapse.py`
+ `.log`. **Moved** — `rescore_corpus.py`/`.log` to `measurements/superseded/`.
**Changed** — `app/detection/{chain,settings}.py`, `app/db/repository.py`
(`pinned_run_discrepancies`), `app/scenario/batch.py`, `measurements/corpus/detection_metrics.py`,
`tests/test_anom_batch_trigger.py` (anom-016's tests moved to the new signature), root `Makefile`
(`RESCORE_CONFIRM`), `measurements/exports/detection/*`.

**New, frontend** — `src/hooks/useEvidenceCollapsed.ts`, `src/test/evidenceCollapse.test.tsx` (14).
**Changed** — `src/components/em/EmEvidencePanel.tsx`.

**Docs** — `CLAUDE.md` (trimmed; repo map; Git section now *work on `main`*), `qa.md` §152,
`thesis_notes.md` (three subsections: the in-series evaluation, the pinned baseline, the measurement
that wrote to the store), `progress_note.html` (report-card figure; figure-text colour fix; legend
fix), `measurements/README.md` (re-score section rewritten). The progress note was published once
this session, on 6 October.

## Failed attempts

**The user's reading of the detection metrics was wrong and the docs allowed it.** They took
precision/recall/F1/latency to compare deterministic detection with AI detection. There is no AI
detector; the two comparisons are in series. Corrected in `qa.md` §152, the thesis notes and the
progress note — the fact that it was a natural reading is the reason it needed a figure.

**The handoff's prediction that latency would move under the new baseline was wrong.** It did not;
nothing in the table moved.

**The spec missed the twenty cited runs.** `anom-017` said "re-score every completed run" while
`db-011` forbids that on 20 of them. Found by querying the store before writing tests; the user
chose to refuse and record them.

**The spec also missed that an id is not a content.** A pinned list of ids would silently build a
different baseline on another database. Seeds pinned beside ids, agreed before tests.

**`detection_metrics.py` had been writing to the store it measures** — findings and stamps since
`anom-015`, bundles since `evb-003`. Found only when the post-re-score run stopped at run 102 on
`db-011`. Its partial run re-stamped the corpus runs before 102 under the same pinned baseline
(harmless, stamps re-dated). Fixed by `assess_without_storing`, agreed as a spec amendment.

**I ran the results table without `CORPUS=v2`** and it exited immediately; the old log was saved
first, so nothing was lost.

**Tests that passed against stubs.** Three `anom-017` tests were vacuous on an empty constant or an
empty answer, and two of the measure-without-storing tests passed against a naive stub; all
tightened before implementation. One test wrongly assumed an empty observation list is refused
downstream — it is not; the test was wrong, not the code.

**A commit split went wrong.** A `git add` with a path already moved aborted the whole add, so the
spec flag and scripts landed in a docs commit; the three commits were redone on the branch. The
`git mv` of `rescore_corpus.py` had already gone into the test commit, which was left there since that
test asserts the move.

**One mutant was invalid as written** (removing `try` left a dangling `catch`); rewritten, killed.

**`anom-016`'s end-to-end batch test failed on the pin** — a test database does not hold the pinned
runs, which is the stated consequence. `score_batch` gained a `quiet_runs` parameter and the test
names its own run, as a deliberate re-score would.

## Next step

The panel chain, as its own session, in this order — nothing on it is visible until the last lands:

| | | gated by |
|---|---|---|
| 1 | **`api-016`** — each aircraft track carries the state this run's findings put it in | — |
| 2 | **`api-007`** — server-side view filter with suppressed counts | `api-016` |
| 3 | **`op-007`** — the Anomalous / Nominal / All control | `api-007` |
| 4 | **`op-004`** — the tabbed exception panel, absorbing `op-006`'s timeline | `op-007` |

**Decided this session:** `op-005`'s *View all* link renders **disabled, with a reason**, as
`RESET`/`REPLAY` do — `op-005` stays a later item.

Then, unchanged: the map (`map-001`–`map-004`), `hypotheses`, `eval-006` (waits on a second rater).

Open and unowned:

- **No mutation pass over `anom-017`.** The structural tests are AST checks and the refusal is
  database-tier; worth a pass before the write-up quotes it.
- **The progress note does not yet tell this session's story** — the evidence panel ("the screen
  says why"), the gap closing from 140 hours to 0, and "a measurement writes nothing". Its detection
  figures are still correct; only the story is behind.
- **Three windows now open 40 s before the staged onset** (runs 204, 224, 264; 10 s before, under the
  old baseline). Latency is unaffected; unexplained, and flagged in the thesis notes.
- **The panel's sentence for an unexplained conclusion is stale** — it says the account "was built
  and not kept", which stopped being the reason at `evb-003`. No hour shows it after the re-score.
  One-line copy fix.
- **`detection_metrics.py` still imports `save_findings`**, now unused.
- **A figure quoted 7 times across the docs is stale** ("20.7M observations"; the store holds
  15.5M), inside the grounding-check tractability argument — correct deliberately.
- **`_corpus.py`'s id ranges are stale** in its docstring; nothing depends on the prose.
- **`docs/thesis_notes.md` is misfiled from about line 6900 onwards.**
- **The hour chooser is blind by design**, a pinned hour is not in the URL, and the evidence account
  is fetched per hour rather than polled — all carried from the previous session.
- **0 of 297 stored bundles carry a superseded claim**, so the panel's ruled-out block is unexercised
  on real data.
