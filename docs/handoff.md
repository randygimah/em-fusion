# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-13
**Branch:** `main`, clean. Five commits. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session answered three questions about the first real batch (`docs/qa.md` §54–56) and landed
**`scn-004`**, the Scenario Control screen. **The `scn` area is now 5 of 5** — the scenario
generator is finished. Nothing in the screen is wired to a backend, deliberately.

## Current state

| | |
|---|---|
| Backend suite | **564 passed, 99.93%** via `make test-backend`, database tier live, 132 s |
| Frontend suite | **45 passed** (`pnpm exec vitest run`). **No coverage tooling** — see Failed attempts |
| Spec items passing | **25 of 84** — `scn` **5/5**, `adp` 7/8, `db` 5/7, `api` 3/9 |
| New dependencies | None |

### What exists now

`frontend/src/screens/scenarioControl.tsx` renders the scenario library, a configuration form over
exactly the dials `python -m app.pipeline` accepts, the run controls, a status indicator and the
recent-runs table. It takes `control` plus optional `onStart` / `onReset` / `onReplay`. With no
handlers the controls render **disabled with the reason on screen** rather than hidden, because
`api-006` does not exist.

`frontend/src/types/scenarioControl.ts` is the contract, and `backend/tests/test_scn_control_contract.py`
is what keeps it honest — it parses the TypeScript and compares five shapes against the generator in
both directions, plus one closed-set assertion for `api-009`. The parser was lifted out of
`api-002`'s test into `backend/tests/contracts.py` so one implementation serves both suites.

**The screen is not reachable in a browser.** Nothing routes to it; `App.tsx` still renders the
Operational Picture directly. `nav-001` is what changes that.

### Measurements taken this session

- **What separates two runs of a batch** (base 20220627, twenty runs, reproduced offline and
  matching the batch's report row for row): aircraft **in the window** 514–550, a 7% spread;
  aircraft **in the zone** 13–91, sevenfold, following the seed-derived centre. Randstad centres
  average 85 within 60 km; the southern and eastern four average 19–33.
- **Runs 16 and 17 open two seconds apart**, share a centre, and stage on **the same 90 aircraft** —
  identical sets. They stage 2 and 5, **with no aircraft in common**. Run 8 is a third member of the
  cluster: same centre, 97% overlap, 9 staged, disjoint from both.
- **Window overlap:** 114 of 190 pairs overlap at all, 10 by more than 90%, mean 30%.
- **A matched control costs nothing:** run 0 emitted as `normal-baseline` and as `gnss-degradation`
  at the same seed and window differs in **60 of 5,040 cells (1.2%)** — exactly the incident's
  footprint. The other 4,980 readings are identical values.
- **Test counts:** 556 backend tests before this session's test commit, 564 after. The previous
  handoff said 554, which was two short of the tree it described.

### Mutation results, all from the committed baseline

| Mutation | Red |
|---|---|
| Contract drops a dial the batch accepts | 1 |
| A recorded parameter renamed to camelCase | 1 |
| A sixth scenario type | 1 |
| A listed run carries the answer key | 2 |
| The form defaults to ten runs | 1 |
| The form offers the mockup's noise amplitude | 1 |
| A pause control appears | 1 |
| Replay starts the form's seed under the row's name | 1 |
| A blank seed is invented rather than requested | 1 |
| The controls are live with nothing behind them | 1 |
| An unfinished run reads as complete | 1 |

## Files in flight

Nothing half-built; the tree is clean.

## Changed

Five commits, `4b9e08e` through `e4091e6`: the three Q&A entries with their two evaluation notes;
the `scn-004` spec amendment; the tests; the implementation; the docs pass.

Added: `frontend/src/types/scenarioControl.ts`, `frontend/src/mocks/scenarioControlMock.ts`,
`frontend/src/screens/scenarioControl.tsx`, `frontend/src/test/scenarioControl.test.tsx`,
`backend/tests/contracts.py`, `backend/tests/test_scn_control_contract.py`. Modified:
`backend/tests/test_api_operational_picture.py` (uses the shared parser), `docs/spec.jsonl`
(`scn-004` amended and flipped), `docs/qa.md` (§54–56 and four glossary terms),
`docs/thesis_notes.md` (two Evaluation subsections, two Implementation subsections),
`docs/implementation.md`, `CLAUDE.md`.

## Failed attempts

- **Three tests were written after the implementation**: reset's handler, which no test clicked; the
  spectral-extent control, which no test changed, so nothing proved the value reached the payload;
  and the fallback naming a run whose type the library does not list. All three are behaviours with
  **no assertion** rather than wrong assertions — the class of gap a coverage report finds
  mechanically. **The frontend measures no coverage at all**, so nothing reported them. The backend
  gate caught exactly this kind of gap in `scn-003`. Marked as deviations in their own comments.
- **`pnpm` will not run under the shell's default Node.** Node 20.19.4 against a pnpm that needs
  ≥22.13 fails with `No such built-in module: node:sqlite`, which reads like a broken install.
  `. ~/.nvm/nvm.sh && nvm use` in `frontend/` first; `.nvmrc` pins 24.
- **`biome check --write` reformatted six files this item never touched** — pre-existing drift from
  a config (`attributePosition: multiline`, `lineWidth: 150`) that was never applied. Reverted so
  the commit stayed on subject. The drift is still there and is listed below.
- **A mutation patch did not apply** because biome had collapsed the five-member union onto one
  line after it was written. Mutation patches are written against the *formatted* file, not against
  what was typed.
- **The test file's handler types had to be rewritten** once the contract existed. They were
  `Record<string, unknown>` at the test stage, deliberately, so the parity tests would be red; a
  real `ScenarioConfiguration` is not assignable to it, so `tsc -b` failed at the retyping step and
  not before.

## Next step

1. **`nav-001` — the three-entry nav rail.** Small, and it is what makes `scn-004` reachable:
   `App.tsx` renders one screen today. Local state rather than a router — no new dependency — and
   Hypotheses is an explicitly empty destination until `hyp-*` exists.
2. **`api-006` — the scenario endpoints.** The screen's controls are disabled until these exist, and
   the contract that names them is already parity-checked against the generator. It carries one open
   design question: a batch takes about 70 s and writes ~510k rows, and the project has no task
   queue by scope, so `POST /scenario/start` has to decide between blocking, a background task, and
   a queued row the frontend polls.
3. **Phase 8** — baseline engine, then the deterministic detectors. The first thing that will ever
   read an answer key.

Owed, with an owner but no date:

- **Decide whether the five batches share one base seed.** Recommended, and measured: it makes each
  control a counterfactual of its scenario run rather than an independent sample of quiet. Belongs
  to `eval-001` with the question of whether the incident dials vary within a batch. Both must be
  settled before the scoring campaign is generated.
- **Decide on frontend coverage tooling** (`@vitest/coverage-v8`). A new dependency, so not taken
  mid-item; the argument for it is now evidence rather than principle.
- **Run `pnpm format` across the frontend** as its own `style:` commit, or drop the formatter config
  that nothing enforces.
- **The form does not refuse an incident that starts after its run ends.** The batch does, with the
  message that produced twenty mislabelled controls. Catching it in the form would be better than
  catching it in a batch report, and it needs a spec line before a test.
- **Pause diverges from `FR-714`** — not built, recorded in the spec item and `thesis_notes.md`.
  Revisit if `api-006` gains a lifecycle.
- **A run row cannot distinguish a run still going from one that died.** Absence of `completed_at`
  covers both, so the screen says "incomplete" and no more. A status column or `api-006` fixes it.
- **`op-001`'s badge must key off the run, not off an observation's data mode.**
- **A floor on the affected-aircraft count** rather than a bare 8%, once the detectors exist.
- **Record the measured false-positive rate on the coverage-gap type with and without the
  exclusion** — the gap left in `thesis_notes.md` when `adp-008` landed.
- **Confirm the digest survives an x86-64 run.** The first CI job produces this for free.
- **Detector radii for `anom-005` and `anom-007`** from the measured band [55.7, 85.7) km.
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
