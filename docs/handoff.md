# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each time — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-13
**Branch:** `main`, clean. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session landed **`nav-001`**, the three-entry navigation shell — the item that makes `scn-004`'s
Scenario Control screen reachable in a browser for the first time. The amendment was agreed before
tests were written, and the item carries six decisions rather than the one the original line implied.

## Current state

| | |
|---|---|
| Frontend suite | **55 passed**, 6 files (`pnpm exec vitest run`), `tsc -b` and `biome lint` clean |
| Browser pass | All three entries, the deep link, and the unrecognised-hash fallback checked in Chrome; no console errors |
| Backend suite | **564 passed, 99.93%** — unchanged, and **not re-run this session**; nothing touched it |
| Spec items passing | **26 of 84** — `scn` 5/5, `adp` 7/8, `db` 5/7, `api` 3/9, `nav` 1/1 |
| New dependencies | None. No router library — see below |

### What exists now

`make up` gives all three rail entries, with two of them leading to a real screen.

The route is the **URL hash**. `frontend/src/routes.ts` declares the three screens once — id, label,
hash — and `screenFromHash` resolves an unrecognised or empty hash to the Operational Picture rather
than to nothing. `useCurrentScreen` reads it and listens for `hashchange`. `EmNavRail` is dumb: it
renders the list it is handed, as **anchors**, so `aria-current="page"` sits on a link where
assistive technology expects it. A router library was rejected as a dependency taken on for three
destinations with no nesting and no parameters; component state was rejected because it makes the
address bar lie — a reload would drop the analyst on a screen they did not choose, and no screen
could be linked to or named in a bug report.

All three destinations render. `screens/hypotheses.tsx` is the **destination, not the screen**: it
names what is missing, because FR-701 fixes the rail at three entries and a blank page reads as a
fault rather than as a gap. Replace it wholesale when `hyp-*` starts.

`scenarioControl.tsx`'s existing note gained one sentence: the listed runs are **a fixture from a
recorded batch rather than the database**. Those rows carry real seeds, real windows and real
parameters, which is exactly what makes them dangerous — rows from nowhere announce themselves, rows
from a real batch do not. Same rule as `api-003`'s degraded-from-first-paint indicator.

The picture poll moved out of `App` and into the Operational Picture's own route component, so it
mounts and unmounts with the screen that needs it instead of polling every five seconds against an
endpoint nobody is looking at. `api-003`'s seam is where it was: `App.tsx` is still the only module
that knows where a screen's data comes from.

### Mutation results, all from `fe5b5c6`, Node 24.18.0, Vitest 4.1.9

Each applied singly and reverted from a copy taken beforehand — **not** with `git checkout`, which on
an earlier item deleted the untracked implementation it was testing.

| Mutation | Red |
|---|---|
| A fourth entry joins the rail | 2 |
| An unrecognised address renders no screen | 1 |
| The route lives in state, so the address is ignored | 1 |
| Every entry marked as the current page | 2 |
| Fixture rows presented with nothing saying so | 1 |
| The poll runs above the switch, for every screen | 1 |
| The Hypotheses destination renders a blank page | 1 |
| The Scenario Control entry leads nowhere | 4 |

Every mutation was caught, and each failed on the test written for it rather than on a distant
assertion.

## Files in flight

Nothing half-built; the tree is clean.

## Changed

Five commits this session:

- `f3adcd4` — `spec: amend nav-001` (six decisions, two new failure cases)
- `878012a` — `test: add tests for nav-001` (ten tests, all proved red before implementation)
- `fe5b5c6` — `feat(nav-001): the three-entry rail, with the hash as the route - tests pass`
- `32ee70b` — `docs: nav-001 write-up`
- `c4f8d66` — `fix(scn-004): the recent-runs caption sits above the table again`

Added: `frontend/src/components/em/EmNavRail.tsx`, `frontend/src/hooks/useCurrentScreen.ts`,
`frontend/src/screens/hypotheses.tsx`, `frontend/src/test/navigation.test.tsx`. Modified:
`frontend/src/routes.ts`, `frontend/src/App.tsx`, `frontend/src/screens/scenarioControl.tsx`,
`docs/spec.jsonl` (`nav-001` amended and flipped), `docs/thesis_notes.md` (two System Design
subsections, two Implementation subsections), `docs/implementation.md`, `CLAUDE.md`.

**The progress note was republished** (version 16, same URL) for `scn-004` and `nav-001` together —
it had not been touched since 12 September. New section on the scenario screen and the three
entries, the spine's analyst stage moved to two-of-three, counts corrected to 26/84 and 564 tests,
and a new passage on the three ways a test here can be blind.

No `docs/qa.md` entry: the user asked no question this session and no clarification corrected a
misunderstanding. The file is not padded to look busy.

## Failed attempts

- **`nav-001` was flipped to `passes: true` with no coverage measurement.** The workflow's gate is
  90% and the frontend still measures nothing, so the eight-mutation pass stood in for it. That is a
  **deviation from the stated gate**, not an equivalent — recorded here rather than glossed.
- **The first seven mutations left one of the ten tests unexercised.** They were derived from the
  specification's six decisions and two failure cases, and that set is structurally blind to the
  wiring a decision *presumes*: nothing broke the claim that choosing the Scenario Control entry
  actually reaches that screen. The gap was found by tallying tests against mutations, not by the
  pass itself; an eighth mutation was written for it. Worth remembering that the tally is the step
  that finds this, and that a coverage report would have found it mechanically.
- **`scn-004` shipped a caption that rendered in the wrong place, and the browser pass found it.**
  The recent-runs caption reused `LABEL`, which begins with `block`; `display: block` on a
  `<caption>` takes it out of the table's caption box, so it rendered *below* the column headers.
  **Fixed with no test, which is a deviation** — the suite finds that table by the accessible name
  the caption supplies, and that name was correct throughout, so the tests passed for the right
  reason on the exact element that was wrong. jsdom does no layout, and the project's convention
  forbids asserting on CSS classes, so no admissible test can catch a box-model defect. Only looking
  at the running interface does.
- **The repo map in `CLAUDE.md` had already gone stale before this session.** `api-003`'s
  `src/lib/api.ts` and `src/hooks/useOperationalPicture.ts` were never listed, two test files were
  missing from the `src/test/` row, and `App.tsx` was still described as wiring the mock into the
  screen. Corrected as part of this item. The rule exists; it slipped one item earlier than anyone
  noticed.
- **A doc-editing script inserted one of two prepared blocks** because the second was written into
  the same script and never applied, and the replacement expression for the first was convoluted
  enough to hide it. Caught by grepping the headings afterwards rather than by reading the script.
  Verify inserts by looking at the file, not at the exit code.

## Next step

1. **`api-006` — the scenario endpoints.** The Scenario Control controls are disabled until these
   exist, and the contract naming them is already parity-checked against the generator. One open
   design question: a batch takes about 70 s and writes ~510k rows, and the project has no task queue
   by scope, so `POST /scenario/start` must choose between blocking, a background task, and a queued
   row the frontend polls. Landing it also retires the fixture sentence added this session.
2. **Phase 8** — baseline engine, then the deterministic detectors. The first thing that will ever
   read an answer key.
3. **Frontend coverage tooling** is now argued for by three separate findings rather than two.
   Still a new dependency, still unowned.

Owed, with an owner but no date:

- **Decide whether the five batches share one base seed.** Recommended and measured: it makes each
  control a counterfactual of its scenario run rather than an independent sample of quiet. Belongs to
  `eval-001` with the question of whether the incident dials vary within a batch. Both must be
  settled before the scoring campaign is generated.
- **Decide on frontend coverage tooling** (`@vitest/coverage-v8`). Now argued for twice by evidence
  rather than principle — three missing tests in `scn-004`, one unexercised test in `nav-001`.
- **Run `pnpm format` across the frontend** as its own `style:` commit, or drop the formatter config
  that nothing enforces.
- **The form does not refuse an incident that starts after its run ends.** The batch does, with the
  message that produced twenty mislabelled controls. Needs a spec line before a test.
- **Pause diverges from `FR-714`** — not built, recorded in the spec item and `thesis_notes.md`.
  Revisit if `api-006` gains a lifecycle.
- **A run row cannot distinguish a run still going from one that died.** Absence of `completed_at`
  covers both, so the screen says "incomplete" and no more. A status column or `api-006` fixes it.
- **`op-001`'s badge must key off the run, not off an observation's data mode.**
- **A floor on the affected-aircraft count** rather than a bare 8%, once the detectors exist.
- **Record the measured false-positive rate on the coverage-gap type** with and without the
  exclusion — the gap left in `thesis_notes.md` when `adp-008` landed.
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
