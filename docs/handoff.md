# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: replayed aviation telemetry and synthetic RF observations are fused through a Data
Abstraction Layer, deviations are detected deterministically, and evidence bundles become
schema-validated, grounding-checked AI hypotheses for an analyst to review. Decision support, not
autonomous decision-making.

This session set out to build `evb-002`, evidence traceability — the check that every statement in
an evidence bundle resolves to a stored observation, so the grounding check in `ai-008` has a closed
set to verify a model's citations against.

## Current state

**`evb-002` is built and green. 47 of 98 spec items pass.**

- 999 tests pass on the full backend tier, **99.83% coverage**, 100% on the new module. Ruff and
  mypy clean.
- Mutation pass: **27 of 29 killed**, both survivors provably equivalent and declared in the harness.
- Migration `0005_evidence_bundle_columns` is at head and reversible.

Measurements taken this session, so the next one need not re-derive them:

| Question | Answer |
|---|---|
| How many observations does a real bundle cite? | **26 at the median, 105 at the worst**, over 24 bundles from 40 runs. A zone bundle cites 79 at the median, a fault bundle 23. |
| How many evidence items cite nothing? | **72 of 332** — verdicts, nominal neighbours, rate ratios. All genuine judgements. |
| One query per citation, or one per shape? | **Per shape.** 10.5 ms against 194.5 ms at the median, **18.6x**. |
| Is the composite index owed before this item? | **No.** Batching removes the cost the index would have removed. It stays a candidate. |
| Did every citation resolve? | **No — 91 of 1,021 resolved to zero rows**, every one the start of a `frozen_position` finding. Fixed. |

What `evb-002` does, in one paragraph: resolution is by coordinate, batched one query per shape per
bundle, always scoped to the scenario run, over a closed set of exactly two coordinate shapes
matched by exact key set. Zero rows and more than one row both raise. Atomicity is per run — every
bundle is resolved in full before anything is written — and the write replaces the run's bundles,
following `db-008`. Resolved ids are persisted per item inside the evidence JSON, not in a join
table.

Unchanged and still open: the broadband generation arm (blocks `anom-007`'s confidence bands and
`evb-001`'s frequency-adjacency corpus demonstration); the frontend suite exits non-zero
(`control.runs.map is not a function` at `scenarioControl.tsx:344`); nine measurement scripts still
select runs by means other than `_corpus`; `DEFAULT_AFFECTED_FRACTION` is inert.

## Files in flight

The tree is clean. Everything below is committed.

## Changed

| Commit | What |
|---|---|
| `b35c4bb` | `measure:` the bundle ref-cost measurement and its log |
| `52e9f11` | `docs:` `qa.md` §83 and three glossary rows |
| `8d14f11` | `spec:` `evb-002` composition, plus amendments to `anom-010`, `db-008`, `evb-001` |
| `2496530` | `test:` 30 tests for `evb-002`, all red |
| `61dbda6` | `feat(evb-002):` the resolver, the persistence, migration `0005` |
| `650d5a0` | `test:` close 4 mutation survivors |

New files: `backend/app/db/bundles.py`, `backend/alembic/versions/0005_evidence_bundle_columns.py`,
`backend/tests/test_evb_traceability.py`, `backend/measurements/corpus/bundle_ref_cost.py` (+ log),
`backend/measurements/mutation/mutate_evb002_traceability.py` (+ log).

Modified: `app/detection/bundle.py` (the `Grounding` declaration and `observation_ids`),
`app/detection/track_gap.py` (`observed_at`), `app/detection/findings.py` (cite `observed_at`),
`tests/test_db_findings.py` (two constructions updated), `docs/spec.jsonl`, `docs/qa.md`,
`docs/thesis_notes.md`, `backend/measurements/README.md`, `CLAUDE.md`.

No new dependencies.

## Failed attempts

**I assumed a finding's window start was a time something was observed. It is not, for half the
track findings.** The storable shape wrote the window ends into the citation field. For the
coverage-gap mechanism that is correct — its ends *are* the reports either side of the silence. For
the frozen-position mechanism it cannot be: the start is reconstructed by subtracting the reported
staleness, and that instant is by definition the one moment in the window at which nothing was
recorded. 91 of 1,021 real citations landed there. It had been that way across two corpora and 240
runs, invisible because nothing read the field until `evb-002` did. Written up as `qa.md` §83.

**Two of my first-draft tests passed before any implementation existed**, which the workflow calls a
wrong test. One asserted the coordinate shapes against this test file's own helper functions rather
than against what the rules emit — proving only that the helpers agree with themselves. The other
downgraded one revision from head and asserted a column was absent, which was true before the
migration existed too. Both rewritten to assert positively first.

**Two mutants I was about to write would have survived, which meant two tests were weak.** Writing
the mutation sites before running them caught this: the atomicity test started from an empty table,
where "resolve then delete" and "delete then resolve" are indistinguishable; and the round-trip test
never asserted *where* the event was, so a latitude/longitude transposition in the EWKT would have
passed. Both fixed before the pass ran.

**The first mutation pass killed 22 of 28, and four of the six survivors were real gaps** — all the
same shape as `evb-001`'s. Run scoping is written twice, once per coordinate shape, and only the RF
clause had a test. The observation-type filter had none. And two refusals were asserted with a
pattern that *any* failure message satisfies, so both guards could have been deleted with the suite
still green. A refusal test that does not pin which refusal it got is testing that something went
wrong.

**One mutation anchor never matched** — I wrote it at 8 spaces of indentation where the line sits at
12, and the harness reported it INVALID rather than silently scoring it. That is the harness working
as intended; noted because an anchor that matches *zero* times is the failure mode a less careful
harness would report as a survivor.

**A `:param::type` cast in a test helper was read as a parameter named `payload:`.** SQLAlchemy's
`text()` does this, and it is the second time this session's lineage has hit it — the uniqueness
measurement hit it with `:ts::timestamptz`. `CAST(:payload AS jsonb)` is the form that works.

**I ran `ruff check` over `measurements/` and got 332 errors.** Not a regression: that directory is
deliberately outside linting, as `CLAUDE.md` records. My command was wrong, not the tree.

## Next step

1. **Offer to update the progress note.** `evb-002` changes the story it tells: the pipeline now has
   a checked boundary rather than an asserted one, and the 91-in-1,021 finding is exactly the kind
   of worked example that note exists for. Not yet done.
2. **`ai-008`'s rule-id ambiguity**, owed before that item and not before this one. `anom-012`
   defines no rule id and borrows `anom-010`'s, so a rate-excess item and a discontinuity item carry
   the same id while making different claims. Recommendation unchanged: ground on
   `(rule_id, finding_type)`.
3. **`evb-003` or the AI layer**, whichever the spec puts next — `evb-002` was the last of the
   traceability prerequisites `ai-008` named.

Open and unowned:

- The broadband generation arm. Blocks two things now, not one.
- The frontend suite's failure at `scenarioControl.tsx:344`.
- The composite index on `observations` — measured as *not* needed, kept as a candidate.
- Nine measurement scripts that select runs by means other than `_corpus`.
