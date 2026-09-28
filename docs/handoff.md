# Handoff

*Snapshot, overwritten each session. Last written 28 September 2026.*

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations are fused through a Data Abstraction Layer,
deviations are detected deterministically, and evidence bundles become schema-validated,
grounding-checked AI hypotheses for analyst review.

This session ran the scored campaign to completion, then acted on four pieces of direction: defer the
score ingest until the second rater returns; write a plain-English orientation page for the evaluation
harness; make the scoring pack readable and turn the score sheet into a spreadsheet; and bring the
thesis notes, progress note and handoff up to date.

## Current state

**The tree is clean and everything below is committed.** Backend suite: **1,285 passed, 288 skipped**
(the skips are the `database`-marked tests, which need `TEST_DATABASE_URL`). `app/evaluation` is at
**100%** across all four modules. `ruff` and `mypy` clean; `black --check` still reports the known
**12 files** of pre-existing formatting debt, none of them touched this session.

**The scored campaign has run**, once, on 28 September 2026 against `gpt-4.1-2025-04-14`:

| | Hosted | Template |
|---|---|---|
| Generations | 60 (3/bundle) | 20 (1/bundle) |
| Bundles | 20 | 20 |
| Skipped | 0 | 0 |
| Grounding checked / caught | 60 / **0** | 20 / **0** |
| Fallbacks, refusals | 0, 0 | — |
| Wall time | 334.2 s | 0.008 s |

60 calls of a 200 ceiling; 326,106 prompt + 25,269 completion tokens; **$0.8544**, 0 unpriced.
20 of 20 complete scored pairs. Project spend to date ≈ **$1.75 of $5**.

**The scoring pack has been rebuilt** and is what a marker would now receive:
`backend/measurements/corpus/scoring_pack/` holds `hypotheses.md` and `score_sheet.xlsx` for the
marker, `arm_key.csv` / `arm_key.xlsx` held back, and `score_sheet.csv` as the archival form the
ingest will read. 20 packs, 40 explanations, **200 pass-one values**. A/B balance: A is template on
12 packs, hosted on 8. The blinding scan is clean across **both** marker files.

**`eval-006` is deferred with a stated trigger**, at the user's direction: the second rater is
unavailable until mid-October, so no completed sheets exist. Recorded in `docs/qa.md` §101 with the
argument — the shape of a returned sheet is a fact about what two people did with a file and is not
knowable in advance, and writing the adjudication code while looking at the *first* returned sheet
would be making implementation choices with partial results visible. **Build it when both completed
sheets exist, not before and not between the first and the second.**

## Files in flight

**None. The tree is clean.** Everything below landed.

## Changed

| Commit | What |
|---|---|
| `dad9d43` | `spec: add eval-007, eval-008` |
| `20199a9` | `test: add tests for eval-007, eval-008` — adds `openpyxl` |
| `9f8b8c8` | `feat(eval-007, eval-008)` — the readable pack and the workbook |
| `329fa7f` | the rebuilt pack, from the committed campaign record |
| `b7af154` | `fix(eval-008)` — the sheet accepts the rubric's whole 1–5 scale |
| `7f1318e` | `docs/evaluation_harness.md` + rubric Part A and two change-log entries |
| `a609aa4` | thesis notes: campaign results, two production failures, the pack |
| `120245e` | `qa.md` §97–101, glossary, and the measurements log of record |
| `b96dceb`, `1057ba3` | progress note: the campaign section, progress table, Next tier |

**New files:** `backend/app/evaluation/workbook.py`, `backend/tests/test_eval_workbook.py`,
`docs/evaluation_harness.md`, `scoring_pack/score_sheet.xlsx`, `scoring_pack/arm_key.xlsx`.

**New dependency:** `openpyxl` (with a `[[tool.mypy.overrides]]` entry — it ships no `py.typed`).
**The Docker image needs rebuilding** for anything running in-container that imports it; `make measure`
rebuilds, and did.

**Spec:** `eval-007` and `eval-008` added and passing. Backlog is **62 of 103**.

## Failed attempts

**The workbook's dropdown offered 1/3/5, and that was wrong.** The reasoning — only those three carry
worded anchors — is coherent and contradicts the rubric, which says *"use 2 and 4 for anything in
between"*. Because the analysis reports **quadratic-weighted κ**, computed across the scale actually
used, narrowing it is a silent change to the pre-registered analysis wearing the appearance of a
stricter form. **The unit test asserted my assumption rather than the document and was green.** Caught
only by reading Part A while editing an unrelated sentence in it, which is not a method. Fixed in
`b7af154`; recorded in the rubric change log and `qa.md` §100. The generalisable rule: *where a second
artefact re-implements a pre-registered decision, its test must assert against the source document,
not against the implementation's own constant.*

**My first restructure introduced a blinding leak, and the existing test caught it.** I appended the
between-pack `---` rule inside the section, so it landed after the last hypothesis only — making B's
block end in something A's did not. `test_both_arms_are_rendered_by_the_same_code` failed immediately.
The separator is now joined *between* sections.

**Two of my new tests were wrong before they were red.** One used `finding.subject`; the field is
`source` — it failed with `AttributeError`, not an assertion. One **skipped**, because the fixture
carries no uncertainties, so it proved nothing; it now constructs the repeated uncertainty directly.
A third matched findings to blocks by text and broke on two fixture findings with byte-identical
wording from different sources; it now counts blocks *carrying* a finding, which is what the defect
actually did.

**A doubled heredoc silently swallowed the first spec append** (`.venv/bin/python … || python3 …` with
two `<<'PY'` bodies — the repo root has no `.venv`, stderr was suppressed, and the second command got
EOF). Verified by re-reading the file rather than trusting the exit code.

## Next step

1. **Mutation harnesses for the four evaluation modules.** 88 tests across `sampling`, `statistics`,
   `pack` and `workbook` with nothing yet establishing they are load-bearing. This session alone found
   a test asserting an assumption instead of the rubric, one that skipped, and one that could not tell
   two findings apart — the pattern is established and the figure should not be quoted until a pass
   has run. Note the scope lesson already recorded: a harness must run **every** suite that tests the
   module, or a mutant survives because its test lives in another file.
2. **`eval-006`**, when both completed sheets exist. Mid-October.
3. **Waves 2 and 3 of corpus v2**, owed for `eval-001` / `eval-002` (detection metrics).
4. **`ai-011`'s harness has not been re-run** since its annotation changed — 36 anchors verified still
   matching, but not re-run.

### Open and unowned

- Nothing applies migrations to the **application** database in the ordinary path. `make migrate`
  exists and nothing calls it. This cost one paid model call this session. Worth a spec item.
- Six mutation harnesses lack the guard file + sentinel pattern.
- The credential loader is now a third copy; generalise it.
- `ai-008`'s superseded case has no corpus demonstration.
- The near-miss "rule under another finding type" bucket conflates two mistakes.
- 12 files not Black-formatted (pre-existing).
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- `docs/phase9_hypothesis_layer.md` §8 still says N=1.
- The progress note is published on demand and no standing URL is tracked; `docs/progress_note.html`
  is the master and is current as of this session.
