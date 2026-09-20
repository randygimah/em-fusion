# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness.
It replays real aviation telemetry alongside synthetic RF observations through a Data Abstraction
Layer, detects deviations with deterministic rules, packages each reported event as an evidence
bundle, and turns that bundle into a schema-validated, grounding-checked hypothesis an analyst
reviews. Decision support, never autonomous decision-making.

This session built the first three items of the AI layer: **`ai-001`** (the output schema, landed at
the start), **`ai-002`** (the template hypothesis generator) and **`ai-003`** (the provider-agnostic
interface every generator sits behind).

## Current state

**51 of 99 spec items pass.** Backend suite: **1155 tests, ~99.8% coverage**, ruff and mypy clean
across 58 source files.

`ai-003` is complete:

- `backend/app/ai/service.py` — the interface, the result envelope, the config, the two failure
  categories. `registry.py` — the only module that knows a provider by name. `providers/template.py`
  — `ai-002` behind the interface.
- 64 tests in `backend/tests/test_ai_service.py`; mutation pass **28 of 29**, single survivor proven
  equivalent (a `try/except` that re-raises).
- Extensibility measured: **1 new module + 2 lines in 1 existing file, 0 changes anywhere else**.
  Log at `backend/measurements/extensibility/provider_cost.log`.

`ai-002` (earlier this session): 38 tests, mutation **34 of 35**, and measured over the 41 real
stored bundles — 41 of 41 generated, 0 refusals, 164 of 164 citations grounded, 24 High / 17 Medium.

The published progress note was updated with the whole AI layer and four stale figures; it is
mastered at `docs/progress_note.html` and republished on demand.

## Files in flight

The tree is clean.

Added this session: `backend/app/ai/{template,service,registry}.py`,
`backend/app/ai/providers/{__init__,template}.py`,
`backend/tests/test_ai_{template,service}.py`,
`backend/measurements/corpus/template_hypotheses.py` + `.log`,
`backend/measurements/mutation/mutate_ai00{2,3}_*.py` + `.log`,
`backend/measurements/extensibility/provider_cost.py` + `.log`.

## Changed

- `2e67faf` `spec: amend ai-002`, `57e7d8b` `test: add tests for ai-002`,
  `0e0084b` `feat(ai-002)`, `60c984e` `docs: progress note`
- `d4295a2` `spec: amend ai-003`, `5cea287` `test: add tests for ai-003`, `feat(ai-003)`
- Documentation: `thesis_notes.md` (nine new subsections), `qa.md` 85–87 plus eight glossary terms,
  `measurements/README.md` (three registrations, including `mutate_ai001_schema.py` which `ai-001`
  had left unregistered), the CLAUDE.md repo map, `implementation.md` Phase 9, this file.

## Failed attempts

**Two specification errors, both found by building rather than by reading.** `ai-002`'s citation
grouping exposed the rule-id ambiguity as *behaviour* rather than argument. `ai-003` said "Output: a
validated hypothesis", which cannot be right — `ai-004`, `ai-005` and `db-002` each need the model
id, frozen parameters and verbatim response, so a bare hypothesis forces every arm to carry that its
own way, which is the leak the item forbids arriving by the back door.

**A purity test that was too blunt, and the temptation to relax it.** "No module in the AI package
may contain a provider's name" failed on the interface itself, because `GeneratorKind.TEMPLATE`
spells that word. The right move was not to relax it but to notice two conflated things — the
*stored generator kind* (a database check constraint) and the *provider name* (a registry key). The
check now forbids a **comparison** against the provider name, and is fired at three spellings of a
real violation and two legitimate uses.

**Mutation found one gap in `ai-003` and four in `ai-002`.** The `ai-003` gap was the property
nobody thinks to test: the suite asserted the config object was frozen and never that the parameters
*mapping inside it* was, so a caller holding a live handle could change what every later call ran
under. The four `ai-002` gaps were all tests passing for a reason other than the one they name.

**Real bundles found two prose defects in `ai-002`** that 37 unit tests and a mutation pass could
not: a doubled full stop where a rule's own text already ends in one, and a summary framing a
not-measurable caveat as "the rule's own conclusion".

**`| head -40` killed a measurement mid-run via SIGPIPE again** — second occurrence. Redirect to a
file; never pipe a measurement through `head`.

**`cd backend` when already in `backend`, for the sixth time**, this time creating a stray
`backend/backend/` directory before it was noticed and removed. Use absolute paths in heredocs.

**A CLAUDE.md repo-map edit failed on a bad anchor** and a second edit in the same script never ran
because the first assertion aborted it. Both applied in a follow-up. Third occurrence of this exact
pattern.

## Next step

1. **`docs/phase9_hypothesis_layer.md`** — an explicit precondition on `ai-004`, and now the
   genuine blocker. It has to settle: what comparability between three arms means, the two kinds of
   fallback (now expressible, since `ai-003` named the two failure categories), the spend ceiling
   whose realistic failure is a retry loop, the pinned dated model id, and what sending an evidence
   bundle to a hosted provider means for the rule that no real aircraft identifier may reach one.
2. **`db-002` owes columns.** The `hypotheses` table has no `summary` or `recommended_human_action`
   and names three fields differently from `ai-001`. Nothing can be persisted until this is fixed,
   and it is cheap now and expensive after a campaign.
3. **`ai-008`, the grounding check.** Unusually cheap to validate because the template generator is
   an input whose correct answer is known in advance — anything flagged on a template hypothesis is
   a defect in the check.
4. **`ai-004`**, gated on 1–3.

Open and unowned:

- **Regenerate corpus v2** when `eval-001` is picked up — three seeds in `CORPUS_V2_PLAN.md`, about
  twenty minutes. Every thesis figure needs it; the development batch must never be used for one.
- Nothing yet builds a `GenerationConfig` from the environment. Deliberate: that belongs with the
  first arm that needs a credential, and `backend/.env.example` gains its keys then.
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- Broadband generation arm — no run stages a wide event.
- Nine measurement scripts still select runs by means other than `_corpus.run_filter()`.
- `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` sit at the repository root rather than in `docs/`.
- **Several committed files are not Black-formatted**, so `make format` (and therefore `make check`)
  produces a large unrelated diff: `app/detection/bundle.py` alone is ~430 lines of churn, plus
  `app/db/bundles.py`, `app/pipeline.py`, `app/scenario/incident.py` and five test modules. Found
  while formatting `ai-003` and deliberately **not** fixed inside it — reformatting 900 lines of
  another item's code inside a feature commit hides the feature. Worth one commit of its own that
  does nothing else.
