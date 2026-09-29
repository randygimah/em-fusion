# Handoff

## Goal

EM Fusion is a human-in-the-loop prototype for explainable electromagnetic situational awareness: it
fuses replayed aviation telemetry with synthetic RF observations, detects deviations
deterministically, and turns evidence bundles into schema-validated, grounding-checked AI hypotheses
for analyst review. It is decision support, not autonomous decision-making.

This session closed the two remaining detection inputs `eval-002` needs: **`anom-008`** (the
quiet-run control) and **`anom-011`** (track-gap recall). Closing the second exposed that the whole
detection evidence base had been measured on a corpus that no longer existed, so it also generated
corpus v2 wave 2 and re-ran the entire measurement protocol.

## Current state

Backlog **66 of 104**. Suite **1,344 passed, 288 skipped**; containerised run **1,631 passed at
99.89%**. ruff and mypy clean. Tree clean.

**The corpus finding, which is the session's largest.** Every committed detection log described a
300-run corpus destroyed on 2026-09-19 (`ops-004`). Wave 1 of corpus v2 was regenerated 2026-09-28
sized for the AI campaign only, and **no detection measurement was re-run against it** — so for
eleven days the logs described a corpus that was not in the database and every automated check
passed, because a committed log is a text file and nothing compares it to anything.

Waves 2 and 3 generated, ~6m40s each. **Corpus v2 is complete: 300 runs in three independently
seeded waves** — `1412660662` (ids 81–180), `965530111` (181–280), `655209063` (281–380). It was
finished deliberately **before** `eval-002` computes anything, so the headline metrics are taken
once on a frozen corpus rather than computed and recomputed with results in view. The 60-run
development batch (695081452, ids 21–80) is separate and no thesis figure may come from it.

All six protocol scripts re-run and diffed at both wave 2 and wave 3. **Every conclusion replicated,
and at the completed corpus size six of the ten headline figures are identical to the destroyed
corpus's** — on seeds drawn independently of the originals, so replication rather than recovery.

| Measurement | Destroyed corpus | Corpus v2, complete |
|---|---|---|
| Sensor fault claimed on its own arm | 60 of 60 | **60 of 60** |
| Interference misattributed as fault | 0 of 60 | **0 of 60** |
| Ladder: every arm decided correctly | 60 of 60 | **60 of 60** |
| Fusion candidate raised on interference | 60 of 60 | **60 of 60** |
| Rate-excess ratio, median | 9.61 | **9.90** |
| Clearing the 1.58 bar | 58 of 60 | **58 of 60** |
| Staged beats its own control | 57 of 60, 3 ties | **59 of 60, 1 tie** |
| Zones with no measurable track evidence | 41 of 60 | **41 of 60** |
| Quiet runs showing the analyst anything | 0 of 20 | **0 of 60** |

The two that differ move in opposite directions. Separation improved to 59 of 60 with one tie. And
the **minimum rate-excess ratio is 0.39** where the old corpus's was 1.00 — a run with *fewer*
dropouts inside the incident window than outside it. It appeared at n=40 and survived to n=60
**without a second example**, so it is one observation rather than a tail. Worth following up.

**`anom-008`** — 29 tests, 100% coverage, mutation **30 of 30**. Bands at n=60: RF **0–0** (60 of 60
zeros), track continuity **8–22**, clusters **4–10**, rate excess **0–0**. Wave 2 widened two of the
four and **wave 3 moved none at all** — the bands have converged, and the RF floor held at zero
through two further independently seeded waves rather than by accident on one. Result: **0 of 60
quiet runs show the analyst anything, over two of the three reportable types** — `anom-006` has no rule and is reported *not exercised*, never clean.

**`anom-011`** — recall against the answer key, both waves and combined:

| Type | Wave 1 | Wave 2 | Wave 3 | Combined |
|---|---|---|---|---|
| `gnss-degradation` | 83% | 81% | 83% | **82%** |
| `aircraft-coverage-gap` | 64% | 59% | 53% | **59%** |
| `ambiguous-mixed-evidence` | 64% | 59% | 53% | **59%** |
| All (900 staged aircraft) | 70% | 66% | 63% | **67%** |

**The third wave separated a stable mechanism from a variable one, and that is the result rather
than the average.** The navigation arm replicates almost exactly (83/81/83), so 82% is a property of
the frozen-position mechanism. The suppression arms spread eleven points (64/59/53) and account for
the whole drift in the combined row — so a single-wave figure for them carries about ±5 points. One
wave would have stated both with equal confidence, which is what the two-batch constraint exists to
prevent, now demonstrated rather than asserted.

Loss account closes exactly: **136 on ground, 132 below threshold, 33 contact not fresh, and zero to
the interior filter, zero absent, zero unbracketed.** Two of the four suspected causes account for
everything, two for nothing. 16 of 900 answer-key aircraft parked (was 209 of 381 pre-`scn-006`); no
run staged nothing, so `eval-002`'s exclusion count is zero on this corpus. Mutation **14 of 14**.

**The two suppression arms are byte-identical in every column** — same mode at a shared seed. One
measurement printed twice, not two. Recorded so nobody reads it as replication.

Standing, unchanged: nothing applies migrations to the application database in the ordinary path;
six mutation harnesses lack guard+sentinel; `ai-011`'s harness not re-run; credential loader not
generalised; `ai-008`'s superseded case has no corpus demonstration; frontend suite exits non-zero
(`control.runs.map is not a function`, `scenarioControl.tsx:344`); `phase9_hypothesis_layer.md` §8
still says N=1; **12 files not Black-formatted** (`make format` fixes them; it is its own commit).

## Files in flight

None. Tree clean at `59f963e`. Progress note published, v18.

Added this session: `backend/app/detection/control.py`, `backend/tests/test_anom_control.py`,
`measurements/corpus/quiet_run_background.py` + `.log`,
`measurements/mutation/mutate_anom008_control.py` + `.log`,
`measurements/corpus/track_gap_recall.log`, `measurements/mutation/mutate_anom011_sensitivity.log`.

## Changed

| Commit | What |
|---|---|
| `bac7810` | `spec: refine anom-008` |
| `a6ad5d3` | `test: add tests for anom-008` |
| `0de2fef` | `feat(anom-008): the quiet-run control - tests pass` |
| `5716474` | `docs: anom-008 write-up` |
| `32fe22e` | `docs: progress note — latency and the quiet-run control` |
| `6535640` | `docs: qa §109 — the register, and the three numbers in a band` |
| `eb4ad9a` | `measure: track-gap recall on corpus v2, with a log that survives` |
| `f8dc29b` | `measure: corpus v2 wave 2 generated, and the whole protocol re-run` |
| `75ae8ea` | `feat(anom-011): track-gap recall on two independently seeded batches - tests pass` |
| `5768a30` | `docs: progress note corrected after the re-measurement` |
| `f60f16a` | `docs: handoff after anom-008 and anom-011` |
| `59f963e` | `measure: corpus v2 wave 3 — the corpus is complete and frozen` |

Documents: `spec.jsonl` (`anom-008` refined + passing, `anom-011` amended + passing), `qa.md`
(§105–109, eight glossary terms, **five run-together rows repaired** — a previous session wrote
literal `\n` into the table), `thesis_notes.md` (nine subsections), `detection_layer.md` (two new
sections, every figure re-stated), `implementation.md`, `measurements/README.md` (re-measurement
banner, two new rows, **sixth hazard**), `CLAUDE.md` (repo map: `control.py`, and `sensitivity.py`
which had never been in it), `progress_note.html` (published, v17).

## Failed attempts

- **`anom-011` looked like a measurement away from closing and was not.** Its figures were on corpus
  v1 with no surviving log, and corpus v2 held one batch against a two-batch constraint. Checking
  that before starting is what turned up the eleven-day gap.
- **The register nearly omitted the unbuilt rule.** Absent, the control would have reported zero
  `possible_data_source_issue` on every quiet run — the absence of a rule quoted as its accuracy.
- **"Silence means the detector did not look" nearly went in as a blanket rule.** It would have
  failed 100% of quiet runs: the RF grid is synthetic and raises nothing on 40 of 40. Fixed by
  moving the requirement into the measured band.
- **A mutation survivor that was not one.** `absent aircraft dropped from denominator` replaced
  `set(staged_aircraft)` with `{a for a in staged_aircraft}` — the same expression. It sent me
  looking for a test that already existed. **A false survivor is worse than a missing mutant**: a
  survivor is a claim about the suite, and acting on it adds a test that passes for the wrong
  reason. Not catchable by AST comparison. Recorded as the sixth hazard.
- **A mutant killed at import scores nothing.** Keying the register on the rule id alone broke
  collection, so the harness reported *inconclusive* — correct, and the second time in two items.
- **`control.py` hit 100% line coverage with two guards untested.** Found by `term-missing`.
- **`as_json` dropped the band's `runs`**, reintroducing at the export boundary what `Background`
  refuses to be constructed without. The suite was green before and after; now pinned by a test and
  a mutant.
- **`make format` reformatted 12 unrelated files.** Reverted, twice. Still open.
- **Two shell mistakes worth not repeating:** the Bash tool's working directory persists between
  calls, so a `cd ..` left three measurements running from `backend/` where the Makefile does not
  exist — they produced empty output and the diffs read "IDENTICAL". Use absolute paths. And a
  Python patch script asserted before writing, so one failed assertion silently discarded two
  substitutions that had matched.

## Next step

1. **`eval-002`** — precision, recall, F1, FPR, FNR, latency per scenario type. **All three
   detection inputs now exist**: latency (`anom-009`), false positives (`anom-008`), recall
   (`anom-011`). Constraints already on the item: a staged-type run that staged nothing is excluded
   from *every* metric with the exclusion count reported (zero on this corpus); the false-positive
   rate must be quoted as covering **two reportable types of three**. **Precision, F1 and latency
   have never been computed at all.**
2. **`eval-003`** — CSV/JSON metrics export. Gated on `eval-002`.
3. **`eval-006`** — deferred to mid-October, when the second rater returns.

Open and unowned:

- **The 0.39 rate-excess run**: dropouts *less* frequent during the incident than outside it. It
  survived from n=40 to n=60 with no second example, so it is a singleton rather than a tail.
- Mutation harnesses for the four evaluation modules — 104 tests with nothing establishing they are
  load-bearing.
- Only `mutate_anom009_latency.py` and `mutate_anom008_control.py` check that a mutant parses.
- The 12 unformatted files; the frontend suite failure.
