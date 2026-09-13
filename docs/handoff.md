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

This session landed **`nav-001`** (the three-entry rail, which made `scn-004` reachable at all) and
**`nav-003`** (that rail collapsing to a 56px icon rail), fixed a caption defect `scn-004` had
shipped, and republished the progress note for all of it.

## Current state

| | |
|---|---|
| Frontend suite | **67 passed**, 7 files, `tsc -b` and `biome lint` clean |
| Backend suite | **564 passed, 99.93%** — unchanged, and **not re-run this session**; nothing touched it |
| Spec items passing | **27 of 85** — `scn` 5/5, `adp` 7/8, `db` 5/7, `api` 3/9, `nav` 2/3 |
| New dependencies | None. No router library, no icon library |
| Browser-verified | Both nav items driven by hand in Chrome; see Failed attempts for what that found |

### What exists now

`make up` gives three rail entries, two of which lead to a screen, and the rail now collapses.

**Route (`nav-001`).** The URL hash. `routes.ts` declares the three screens once — id, label, hash,
and now the icon — and `screenFromHash` resolves an unrecognised or empty hash to the Operational
Picture. `EmNavRail` renders the list it is handed as **anchors**, so `aria-current="page"` sits on a
link. A router library was rejected as a dependency for three destinations with no nesting and no
parameters; component state was rejected because it makes the address bar lie.

**Collapse (`nav-003`).** Two widths: 280px with labels, 56px with icons. The toggle is a **button**
with `aria-expanded` — the exact inverse of why the entries are links. Collapsing hides labels, never
entries: all three keep their accessible names, so the rail reads identically to assistive technology
at either width. The preference lives in guarded `localStorage`, **not** the hash; the reasoning is
`docs/qa.md` §57 and it is the distinction to reach for if this is ever revisited. Expanded is the
default, including whenever storage is absent, corrupt or unreadable.

Icons are hand-authored SVG path data **carried on the route declaration**, which keeps `nav-001`'s
single-list rule intact — a fourth screen cannot be added somewhere that has no icon.

### Mutation results

`nav-001`, eight mutations from `fe5b5c6`: all caught, each on the test written for it. Table in
`thesis_notes.md`.

`nav-003`, eleven mutations from the tree at `a2f508b`, Node 24.18.0, Vitest 4.1.9. Nine caught
cleanly. **Two survived**, both recorded below.

## Files in flight

Nothing half-built; the tree is clean.

## Changed

Eight commits: `f3adcd4` `878012a` `fe5b5c6` `32ee70b` (nav-001 spec, tests, code, docs);
`c4f8d66` (the caption fix); `e196270` (progress note); `5f698a0` `d95d5c6` `a2f508b` (nav-003 spec,
tests, code).

Added: `frontend/src/components/em/EmNavRail.tsx`, `frontend/src/hooks/useCurrentScreen.ts`,
`frontend/src/hooks/useRailCollapsed.ts`, `frontend/src/screens/hypotheses.tsx`,
`frontend/src/test/navigation.test.tsx`, `frontend/src/test/navCollapse.test.tsx`. Modified:
`frontend/src/routes.ts`, `frontend/src/App.tsx`, `frontend/src/screens/scenarioControl.tsx`,
`docs/spec.jsonl`, `docs/thesis_notes.md`, `docs/qa.md` (§57 and two glossary terms),
`docs/implementation.md`, `CLAUDE.md`, `DESIGN.md`.

**The progress note was republished** (version 16, same URL) for `scn-004` and `nav-001`. **It does
not yet cover `nav-003`.**

**`DESIGN.md` was amended**: its Panels section said sidebars have fixed widths. The expanded width is
unchanged but "fixed" stopped being true, so the two states are recorded there. Root file only — the
per-screen copies under `frontend/src/assets/Design` are generated references.

## Failed attempts

- **A width transition, added for polish, broke the feature it decorated.** Collapsing flipped
  `aria-expanded`, wrote the preference, kept all three entries and the current-page marker, left the
  address alone — **and the rail stayed 280px wide.** Mounting the page *already* collapsed rendered
  56px correctly. The transition left the element at its old used width when the class changed. It
  was removed rather than debugged, because `nav-003` had already scoped the animation out as
  cosmetic. **The suite was green before and after**; only driving it in a browser showed it.
- **One of my `nav-003` tests could not fail.** "Keeps all three entries, with their names, when
  collapsed" passed unchanged with the label deleted outright, because a collapsed entry also carries
  a tooltip and a tooltip supplies an accessible name when nothing else does. It was measuring the
  tooltip. Strengthened to assert the label text as well, and the mutation now turns it red. Found by
  mutation, **after** the test was written — a deviation from the order this project works in.
- **The other surviving mutation is the width itself, and it stays surviving.** No test in this stack
  can see it: jsdom does no layout, and the convention forbids asserting on CSS classes. `nav-003`
  predicted this in writing before any code, and it produced a real defect within the hour. A blind
  spot named in advance is still a blind spot.
- **I drafted the whole spec item as `nav-002` before checking the id was free.** It was not —
  `nav-002` is the system-health strip (FR-702), which is precisely the item the new one had to
  constrain. Renumbered to `nav-003`, and the collision improved it: decision six now names `nav-002`
  instead of gesturing at an unbuilt strip. **Check the id before writing the item.**
- **Two browser clicks at coordinates derived from a screenshot missed the toggle.** The page runs at
  devicePixelRatio 1.8, so the screenshot frame is not CSS pixels. Read the element's rect from the
  page and convert, or click via script — do not scale by eye.
- **A long diagnostic session against the live DOM produced readings I then had to throw away.**
  Repeated script clicks plus inline style edits left the component in a state where width readings
  raced the transition, and a `navigate` to the same URL+hash does not reload. Reload properly and
  measure once.
- **`scn-004` shipped a caption that rendered in the wrong place**, found by the same browser pass and
  fixed in `c4f8d66`. `display: block` on a `<caption>` takes it out of the table's caption box.
  **Fixed with no test**, which is a deviation: the suite finds that table by the accessible name the
  caption supplies, and that name was correct throughout.
- **`nav-001` and `nav-003` were both flipped to `passes: true` with no coverage measurement.** The
  gate is 90% and the frontend still measures nothing; mutation stood in. A deviation, not an
  equivalent.

## Next step

1. **`api-006` — the scenario endpoints.** The Scenario Control controls are disabled until these
   exist, and the contract naming them is already parity-checked against the generator. One open
   design question: a batch takes about 70 s and writes ~510k rows, and the project has no task queue
   by scope, so `POST /scenario/start` must choose between blocking, a background task, and a queued
   row the frontend polls. Landing it retires the fixture sentence on the Scenario Control note.
2. **Phase 8** — baseline engine, then the deterministic detectors. The first thing that will ever
   read an answer key.
3. **The progress note does not cover `nav-003`.** Small change to the story; fold it in next time the
   note is touched rather than republishing for it alone.

Owed, with an owner but no date:

- **Decide whether the five batches share one base seed.** Recommended and measured: it makes each
  control a counterfactual of its scenario run rather than an independent sample of quiet. Belongs to
  `eval-001` with the question of whether the incident dials vary within a batch. Both must be
  settled before the scoring campaign is generated.
- **Decide on frontend coverage tooling** (`@vitest/coverage-v8`). Argued for by four findings now:
  three missing tests in `scn-004`, one unexercised test in `nav-001`, one test that could not fail in
  `nav-003`, and the caption defect none of them could see.
- **`nav-002`, the system-health strip, inherits a question from `nav-003`**: what it shows at 56px.
  It must not be answered by letting a collapse hide health — the posture `op-001` takes for the
  data-mode badge.
- **Run `pnpm format` across the frontend** as its own `style:` commit, or drop the formatter config
  that nothing enforces.
- **The form does not refuse an incident that starts after its run ends.** The batch does, with the
  message that produced twenty mislabelled controls. Needs a spec line before a test.
- **Pause diverges from `FR-714`** — not built, recorded in the spec item and `thesis_notes.md`.
- **A run row cannot distinguish a run still going from one that died.** Absence of `completed_at`
  covers both, so the screen says "incomplete" and no more.
- **`op-001`'s badge must key off the run, not off an observation's data mode.**
- **`nav-001` cites FR-709 for the health strip where the requirement is FR-702.** `nav-002` cites it
  correctly and is the authority; the stale ref is in `nav-001`'s amended text.
- **A floor on the affected-aircraft count** rather than a bare 8%, once the detectors exist.
- **Record the measured false-positive rate on the coverage-gap type** with and without the exclusion.
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
