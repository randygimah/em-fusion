# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: replayed aviation telemetry and synthetic RF observations are fused through a Data
Abstraction Layer, deviations are detected deterministically, and evidence bundles become
schema-validated, grounding-checked AI hypotheses for an analyst to review. Decision support, not
autonomous decision-making.

This session built `evb-002` (evidence traceability), then destroyed the generated corpus, then
built the guard that makes that impossible, regenerated a small development batch, and proved the
evidence bundles work end to end on real runs.

## Current state

**48 of 99 spec items pass. 1014 tests, 99.83% coverage, ruff and mypy clean.**

`evb-002` is built and green — 34 tests, 27 of 29 mutants killed with both survivors provably
equivalent. `ops-004` is built and green. `evb-*` is now complete, which means **the AI layer is
unblocked**: `ai-001` is the next item and nothing gates it.

**The database holds a development batch, not a corpus.**

| | |
|---|---|
| Runs | 60 — `normal-baseline`, `rf-sensor-fault`, `gnss-degradation`, 20 each |
| Base seed | `695081452`, recorded in `DEV_BATCH_PLAN.md` before generation |
| Observations | 2,325,288 |
| Selector | `CORPUS=dev`. **No thesis figure may be measured from it** |

Evidence bundles proved end to end through the shipped modules over those 60 runs: 41 bundles, 0
refusals, round trip exact 60 of 60, 2,049 citations resolved to 2,014 distinct rows, both silent
arms producing zero bundles rather than one empty bundle. The negative control — one real citation
shifted by a single second — is refused, with the stored bundle untouched.

Measurements taken this session:

| Question | Answer |
|---|---|
| Citations per bundle | 26 median, 105 worst |
| One query per citation, or per shape? | Per shape — 10.5 ms against 194.5 ms, 18.6x |
| Is the composite index owed? | No. Batching removes the cost it would have removed |
| Did every citation resolve, before the fix? | No — 91 of 1,021 pointed at nothing |
| **How long does generation take?** | **~4 s per run. A full 300-run corpus is ~20 minutes** |

That last figure was never recorded before and changes the cost of regeneration from unknown to an
afternoon's sub-task.

Unchanged and still open: the broadband generation arm; the frontend suite exits non-zero
(`control.runs.map is not a function` at `scenarioControl.tsx:344`); nine measurement scripts still
select runs by means other than `_corpus`; `DEFAULT_AFFECTED_FRACTION` is inert.

## Files in flight

The tree is clean. Everything below is committed.

## Changed

| Commit | What |
|---|---|
| `b35c4bb` | `measure:` bundle ref-cost measurement and log |
| `52e9f11` | `docs:` qa.md §83 — a window is not a time anything was observed |
| `8d14f11` | `spec:` evb-002 composition; amendments to anom-010, db-008, evb-001 |
| `2496530` | `test:` 30 tests for evb-002, all red |
| `61dbda6` | `feat(evb-002):` resolver, persistence, migration 0005 |
| `650d5a0` | `test:` close 4 mutation survivors |
| `96e6566` | `docs:` evb-002 write-up |
| `ed64aff` | `docs:` progress note — the evidence package |
| `d86fa2c` | `spec:` add ops-004 |
| `3cba4c4` | `feat(ops-004):` the test tier refuses a database holding real data |
| `0ec3c9d` | `measure:` pin corpus v2 to its base seeds; DEV_BATCH_PLAN.md |
| `4044114` | `measure:` bundles work end to end on 60 real runs |
| `b5123c9` | `docs:` qa.md §84 — how the corpus was destroyed |
| `8993626` | `docs:` the corpus incident in thesis notes |
| `851fb62` | `feat(ops-003):` `make measure` |

New: `app/db/bundles.py`, `alembic/versions/0005_evidence_bundle_columns.py`,
`tests/test_evb_traceability.py`, `tests/test_ops_database_guard.py`,
`measurements/corpus/bundle_ref_cost.py`, `measurements/corpus/bundle_end_to_end.py`,
`measurements/mutation/mutate_evb002_traceability.py` (all with logs), `DEV_BATCH_PLAN.md`.

## Failed attempts

**I destroyed the corpus — 540 runs, 20.7M observations.** I passed the application's own database
as `TEST_DATABASE_URL` on hand-written `docker compose run` commands, to skip `make test-backend`.
The database-tier fixture's first act is `DROP SCHEMA public CASCADE`. `conftest.py` had anticipated
this exactly and called two variables *"impossible by construction rather than by care"* — it was
impossible by **convention**, and a convention is a thing a person types. Corpus v2 is regenerable
(seeds recorded by `scn-008`); **corpus v1 is gone permanently**, because its seeds were never
recorded — the precise failure `scn-008` was built to prevent. Written up as `qa.md` §84 and three
thesis-notes subsections; converted into a check as `ops-004`.

**The first version of that guard passed all ten of its unit tests and did not fire.** Pointed
deliberately at the real database, it let eighteen tests drop and rebuild the schema. The suite's
own autouse fixture replaces `DATABASE_URL` with an unreachable placeholder before the guard reads
it, so it compared against the placeholder. Fixed by capturing at import, with a test pinning it.
**Fire a safety interlock at the real hazard once, deliberately, and watch it.**

**`run_filter` would have swept the development batch into corpus v2.** It selected v2 as *any run
carrying a base seed* — true the day it was written, false the moment a fourth batch exists. Caught
and fixed before generating anything; v2 is now pinned to its three seeds by value.

**The first end-to-end log carried unredacted aircraft identifiers.** The redactor existed and was
applied to the finding text but not to `source`, which is the field the identifier lives in. Caught
before commit. A redactor applied per field is a list to keep current.

**`tee ... | head -40` killed the measurement mid-run** via SIGPIPE, and the truncated log looked
like a crash with no traceback.

**Two first-draft `evb-002` tests passed before any implementation existed**, which the workflow
calls a wrong test. One asserted the coordinate shapes against this test file's own helpers; the
other downgraded past a revision that had never added the column.

**Three `cd backend && ...` commands short-circuited** because the shell was already in `backend`,
so the `&&` chain never ran and one patch silently did not apply. Fourth and fifth occurrences of
this in the project. Absolute paths, or check the working directory first.

## Next step

1. **`ai-001`, the hypothesis output schema.** Nothing gates it. Then `ai-002` (template generator),
   `ai-003` (provider interface), `ai-008` (grounding check). None of them needs a corpus — they
   take a bundle — and 41 real bundles are now in the database to develop against.
2. **Owed before `ai-008`:** `anom-012` defines no rule id and borrows `anom-010`'s, so a rate-excess
   item and a discontinuity item carry the same id while making different claims. Recommendation:
   ground on `(rule_id, finding_type)`.
3. **Regenerate corpus v2 when `eval-001` is picked up**, from the three seeds in
   `CORPUS_V2_PLAN.md`. ~20 minutes. Verify against the committed logs rather than assuming it
   reproduced. Every figure quoted in the thesis and the progress note was measured on v2 and stands
   on its committed log until then.

Open and unowned:

- The broadband generation arm. Blocks two things.
- The frontend suite's failure at `scenarioControl.tsx:344`.
- The composite index on `observations` — measured as not needed, kept as a candidate.
- Nine measurement scripts that select runs by means other than `_corpus`.
- `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` sit at the repository root rather than in `docs/`.
