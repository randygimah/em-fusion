# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session (7 October 2026, continuing 6–7 October) took **the panel chain** agreed last session —
`api-016` → `api-007` → `op-007` → `op-004` — and landed all four, so the Operational Picture now shows
its exceptions. Along the way the user asked for a **hot-reloading frontend in Compose**, specified and
built as `ops-006`. Every item followed spec → amendment where reading the code found a gap → failing
tests → code → user review in the browser or API → `passes: true`. Work is committed directly on
`main` (no branches).

## Current state

Backlog **91 of 118** (86 of 117 at the start; `ops-006` was added). Tree clean apart from this
handoff and the progress note being committed; `main` in sync with `origin/main`.

- Backend: **2107 passed, 99.93% coverage** (5571 statements, 4 missed), ruff, Black and mypy clean.
- Frontend: **298 passed** (250 at the start), Biome lint and `tsc -b` clean.
- Mutation: `mutate_op007_view.log` **18 of 18**; `mutate_op004_panel.log` **21 of 21** after one
  survivor (every tab marked selected) was fixed by tightening a test. `mutate_op007_view.py` was
  measured at `f404b62`; `op-004` moved its screen targets, so its screen mutants no longer apply as
  written (README says so) — the same properties are mutated in the panel pass.

### What the screen does now

- **Aircraft state** (`api-016`): every track is `interrupted` (a stored `TRACK-GAP` names its
  pseudonym), `nominal` (examined, nothing named), or `unknown` (no pass stamp). A join, never a
  re-detection; a gap stays intermediate.
- **View filter** (`api-007`): `?view=anomalous|nominal|all`; absent is `all`, unrecognised is 422.
  Filtered in the payload builder over each row's served state (never SQL — a test forbids `app/db/`
  naming a row state). `view: {selected, examined, suppressed: {rfSensors, aircraftTracks,
  timelineEvents}}`. `unknown` rows are admitted by `all` only. The detection summary is never filtered.
- **The switch** (`op-007`): *Anomalous only* default every visit; survives polls and hour changes;
  refetches at once; the "Showing … / Switching to …" line names rows by `view.selected` from the
  payload, never the control.
- **The exception panel** (`op-004`): RF / Tracks / Events tabs, docked along the bottom of a
  one-screen-high layout (`lg:h-dvh`) under the map placeholder; the rail keeps hypotheses and the
  summary; evidence is one scroll down. Tab label = rows shown + a word for what they are (none under
  All or on an unexamined hour); footer names withheld rows by what they are, from `view.suppressed`;
  *View all* disabled with its reason. Columns are payload fields only. The receiver grid and the
  rail timeline are gone — each list is rendered once.
- **`make dev`** (`ops-006`): `frontend-dev` service (profile `dev`, `deps` stage, `./frontend`
  mounted, anonymous `/app/node_modules` renewed each start, `API_PROXY_TARGET=http://backend:8000`,
  `BROWSER=none`) on :1234 with hot reload; nginx on :8080 is still the demo path.

### Measured this session

| Measurement | Result |
|---|---|
| Interrupted aircraft in the final window | run 21 (quiet) 13 of 423; 102: 14/428; 204: 16/446; 420: 10/432 (17 gaps in the run); 480: 17/420 |
| Payload size, anomalous vs all | run 21: 3,145 vs 65,140 bytes (95% smaller); run 420: 3,051 vs 66,629 |
| Run 21 under each view (rf · tracks · events shown / withheld) | anomalous 0·13·0 / 7·410·0; nominal 7·410·0 / 0·13·0; all 7·423·0 |
| Dev-server edit propagation (macOS bind mount) | edit served within 2 s, HMR logged; no polling needed |

## Files in flight

None once this handoff and the progress note are committed.

## Changed

| Commit | Message |
|---|---|
| `30a832d` | `test: add tests for api-016` |
| `a961c6c` | `feat(api-016): each aircraft track carries the state its run's findings put it in - tests pass` |
| `ed95284` | `spec: add ops-006` |
| `ac367c1` | `spec: amend ops-006 -- a deps stage, an unpublished proxy variable, renewed node_modules` |
| `3160ad3` | `test: add tests for ops-006` |
| `6fbc7e6` | `feat(ops-006): make dev serves the working tree through Vite with hot reload - tests pass` |
| `dd220f2` | `spec: amend api-007 -- filter in the builder, what each view admits, absent means all, view metadata` |
| `b347bb9` | `test: add tests for api-007` |
| `2eef767` | `feat(api-007): the picture filters by view server-side and says what it withheld - tests pass` |
| `de46c1f` | `spec: amend op-007 -- what it drives today, rows labelled by served view, selection lifetime` |
| `ac5c6b3` | `test: add tests for op-007` |
| `f404b62` | `feat(op-007): the view control asks the server and the screen says what it hid - tests pass` |
| `0c13db3` | `spec: amend op-004 -- labels and footer follow the view, grid becomes the RF tab, payload columns only` |
| `7544654` | `test: add tests for op-004; re-point op-006 and op-007 tests at the tabs` |
| `8761719` | `feat(op-004): the tabbed exception panel, docked under the map - tests pass` |

**New** — `frontend/devProxy.ts`, `frontend/src/lib/viewVocabulary.ts`,
`frontend/src/components/em/EmExceptionPanel.tsx`, tests `devProxy.test.ts`, `viewFilter.test.tsx`,
`exceptionPanel.test.tsx`, mutation scripts and logs `mutate_op007_view.*`, `mutate_op004_panel.*`.
**Changed** — `app/api/v1/schemas/operational_picture.py` (track state, view models, `_admit`),
`app/api/v1/operational_picture.py` (`view` param), `tests/test_api_operational_picture.py`
(+29 tests, parity map), `tests/test_ops_command_surface.py` (+8), `compose.yaml`, `Makefile`
(`dev`, Dockerfile mount for tests), `frontend/Dockerfile` (`deps` stage), `vite.config.ts`,
`tsconfig.node.json`, the frontend contract, mock, API module, polling hook, `App.tsx`, the
Operational Picture screen; `detectionVocabulary.test.tsx` and `viewFilter.test.tsx` re-pointed at
the tabs. **Docs** — `CLAUDE.md` repo map, `README.md` (`make dev`), `docs/qa.md` §153,
`docs/thesis_notes.md` (five subsections: aircraft state, view filter in the builder, dev loop,
labelling by served view, the exception panel), `measurements/README.md`, `progress_note.html`.

## Failed attempts

**I asked the user to review `api-016` without saying nothing would be visible.** They looked for the
tabs on screen. The handoff had said the chain shows nothing until its last step; I should have
repeated it. Recorded in `qa.md` §153 with the second cause — `:8080` is a static build, which is
what led to `ops-006`.

**I wrote `nominal` as the track state in an unexamined test fixture** (`dataAccess.test.tsx`, during
`api-016`); corrected to `unknown` during `api-007`.

**`api-007`'s full run failed one existing test** — the contract parity map did not list the two new
interfaces. The parity check was doing its job; the map was updated after implementation, a deviation
recorded in the feat commit.

**I ran `biome check --write src` twice** (during `op-007` and `op-004`). It reformatted 26 and then
several files outside the item, because much of the frontend is not in Biome's format and `pnpm lint`
never checks formatting. Both times the unrelated files were restored and only the item's edits
re-applied; use `biome lint` / format only new files.

**One `op-007` test passed before implementation** ("keeps its sentence for a quiet hour") and was
tightened before the test commit. **One `op-004` mutant survived** (every tab `aria-selected`) and the
test was tightened after implementation; re-run 21 of 21.

**The spec contradicted itself twice and was amended before tests each time**: `api-007`'s
2026-10-06 amendment let `unknown` tracks into *anomalous*; `op-004`'s labels and footer were true
under one view only. **The first `op-004` layout put the panel under a fixed-height map box**; the
user asked for it lower, and it was docked at the bottom of a one-screen layout before `passes: true`.

## Next step

1. **The map** (`map-001`–`map-004`): unblocked. Receivers and tracks already carry positions and
   states; `map-003` must read the same filtered payload as the panel so the two cannot disagree.
2. **`op-005`** — the drill-down tables, unfiltered by definition; the panel's *View all* is waiting
   on it (disabled with its reason).
3. Then, unchanged: `hypotheses` (`hyp-*`), `eval-006` (waits on the second rater, mid-October).

Open and unowned:

- **The frontend is not in Biome's format** and nothing checks it (`pnpm lint` is lint only). A
  one-off `biome format --write` commit plus a format check in `lint` would close it.
- **Three windows open 40 s before the staged onset** (runs 204, 224, 264), unexplained; latency
  unaffected.
- **"Tracks (13 interrupted)" on a quiet hour** is correct and may read as an alarm — flagged for the
  evaluation in the thesis notes.
- **The evidence panel's sentence for an unexplained conclusion is stale** ("built and not kept").
- **`detection_metrics.py` still imports `save_findings`**, unused.
- **"20.7M observations" is stale** in seven places (the store holds 15.5M).
- **`_corpus.py`'s id ranges are stale**; **`thesis_notes.md` is misfiled from about line 6900**.
- **A fresh database cannot score batches from the screen** until `BASELINE_QUIET_RUNS` is re-derived
  for it (`anom-017`'s stated consequence).
