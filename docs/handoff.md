# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness.
It replays real aviation telemetry alongside synthetic RF observations through a Data Abstraction
Layer, detects deviations with deterministic rules, packages each reported event as an evidence
bundle, and turns that bundle into a schema-validated, grounding-checked hypothesis an analyst
reviews. Decision support, never autonomous decision-making.

This session built **`ai-002`, the template hypothesis generator** — the first thing in the project
that turns an evidence bundle into an explanation, and the one with no model in it. It follows
`ai-001` (the output schema), which landed immediately before.

## Current state

**50 of 99 spec items pass.** Backend suite: **1091 tests, 99.2% coverage**, ruff and mypy clean
across all 54 source files.

`ai-002` is complete and committed:

- `backend/app/ai/template.py` — 38 tests, mutation pass **34 of 35**, single survivor proven
  equivalent and recorded in the harness.
- Measured over the **41 real stored bundles** from the development batch: 41 of 41 generated,
  **0 refusals**, **164 of 164 citations grounded**, 0 unstable across repeat generation.
  Confidence inherited from the deciding rule comes out **24 High, 17 Medium** — live on real data,
  not a constant. Log committed at `backend/measurements/corpus/template_hypotheses.log`.

Design decisions now fixed and recorded in `docs/thesis_notes.md` and `docs/qa.md` 85:

- **Confidence is inherited, never computed** — read off the bundle's verdict item, which must exist
  exactly once. The two vocabularies (`low` vs `Low`) are joined by **enum member name**, so an
  unrecognised word is refused where the bundle is still in hand rather than laundered by `.title()`
  into something that only fails later at the schema.
- **One citation per kind of evidence**, grouped on the `(rule_id, finding_type)` pair `ai-001`
  defines. A real bundle carries 34 items of 4 kinds.
- **Alternatives are what the ladder already ruled out**, then the standing fault/interference pair,
  then unconditionally the caveat that deterministic rules can only choose among the explanations
  they encode. That last entry keeps `ai-001`'s floor satisfiable for a claim type that does not
  exist yet, so the fallback cannot raise at the moment it is needed.
- **No network, no API key, no model server**, asserted by walking the import graph rather than by
  comment — paired with one test proving the walker works and one firing it at `app/corpus/fetch.py`,
  which genuinely does reach the network.

Measurements are all registered in `backend/measurements/README.md`, including
`mutate_ai001_schema.py`, which had been left unregistered when `ai-001` landed.

## Files in flight

The tree is clean. Nothing is half-done.

Files added this session:

- `backend/app/ai/template.py`
- `backend/tests/test_ai_template.py`
- `backend/measurements/corpus/template_hypotheses.py` + `.log`
- `backend/measurements/mutation/mutate_ai002_template.py` + `.log`

## Changed

- `2e67faf` — `spec: amend ai-002 — confidence inherited, citations grouped on the pair`
- `57e7d8b` — `test: add tests for ai-002`
- `feat(ai-002)` — the generator, both measurements, and the write-ups
  (`thesis_notes.md`, `qa.md` 85 + four glossary terms, `measurements/README.md`, the CLAUDE.md
  repo map, this file, `spec.jsonl` → `passes: true`).

## Failed attempts

**Four tests passed for a reason other than the one they name, and only mutation found it.** The
first pass killed 29 of 34. A refusal test asserted a `TemplateError` whose message names the claim
type — and the *mutant's* fallback path raised too, for a different reason, with a message that also
names it. A count test's two fixtures differed in source count as well as item count, so removing
the count changed nothing measurable. An ordering test asserted the word "rule" appeared in the last
alternative, and the text that displaced it contains that word. A differential test compared actions
across bundle types, where one generic sentence still differed because it interpolates the subject.
All four repairs removed the *accidental* route to the assertion rather than asserting harder.

**Eleven tests passed against a throwaway do-nothing stub**, which is why the stub was written before
the implementation rather than going straight from an import error to code. Four of the eleven were
wrong tests and were strengthened; the nine that remain pass by nature and the suite docstring names
them and says why.

**Two prose defects survived 37 unit tests and a mutation pass and were found by real bundles.** A
doubled full stop, because the fusion rule's not-measurable reason already ends in one and every
fixture I wrote did not; and a summary framing that reason as "the rule's own conclusion" when it is
a statement of what could not be established. Both are properties of what real data contains rather
than of what the code says.

**`| head -40` killed a measurement mid-run again via SIGPIPE** — the second occurrence, and the
`measurements/README.md` note about it exists because of the first. Never pipe a measurement through
`head`; redirect to a file and read the file.

**`mutate_ai001_schema.py` was never registered in `measurements/README.md`** when `ai-001` landed.
Fixed here.

## Next step

1. **`ai-003`, the provider-agnostic hypothesis service interface.** Defined *before* either model
   provider is written, so no provider's request or response shape leaks into it. Needs no corpus
   and no key. This is the natural next item.
2. **`ai-008`, the automated grounding check.** Now unusually cheap to validate, because the
   template generator is an input whose correct answer is known in advance — anything the check
   flags on a template hypothesis is a defect in the check.
3. **`docs/phase9_hypothesis_layer.md`** — recorded as an explicit precondition on `ai-004`, not a
   handoff note. It has to settle: the two model arms plus the deterministic one and what
   comparability means, the two different kinds of fallback, the spend ceiling whose realistic
   failure is a retry loop rather than a price rise, and what sending an evidence bundle to a hosted
   provider means for the rule that no real aircraft identifier may reach one.
4. **`db-002` owes columns.** The `hypotheses` table has no `summary` or `recommended_human_action`
   column and names three fields differently from `ai-001`. This blocks persisting a hypothesis and
   should be picked up before `ai-004`.

Open and unowned:

- **Regenerate corpus v2** when `eval-001` is picked up — three seeds in `CORPUS_V2_PLAN.md`, about
  twenty minutes, verified against the committed logs. Every thesis figure needs it; the development
  batch must never be used for one.
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- Broadband generation arm — no run stages a wide event, so the bundle builder's frequency axis is
  unit-tested only.
- Nine measurement scripts still select runs by means other than `_corpus.run_filter()`.
- `DEFAULT_AFFECTED_FRACTION` is inert.
- `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` sit at the repository root rather than in `docs/`.
