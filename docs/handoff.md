# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session (9 October 2026) built **`op-005`, the drill-down tables**. The exception panel's
*View all*, disabled since `op-004`, now opens an overlay holding the open tab's whole collection for
the hour on screen, always unfiltered. The user chose a full table over the same data (rather than
retiring the item, since *All* already lists every row in the panel) and an overlay (rather than a
screen). Spec → failing tests → code → browser review → mutation → `passes: true`, committed on `main`.

## Current state

Backlog **98 of 121** (97 at the start). Tree clean once this handoff is committed; `main` in sync
with `origin/main`.

- Backend: untouched this session (**2134 passed, 99.93%** at the last run).
- Frontend: **408 passed** (378 at the start); Biome lint and `tsc -b` clean.
- Mutation:

  | Log | Result | Covers |
  |---|---|---|
  | `mutate_op005_drilldown.log` | **31 of 31 (second run; first 30 of 31)** | `op-005` |
  | `mutate_op004_panel.log` | **20 of 20** (re-run; one mutant retired, three anchors re-pointed) | `op-004` |

### What the drill-down does now

- *View all* opens `EmDrillDown` for the open tab: receivers, aircraft or conclusions.
- **The hour** is the one the panel's payload names (`scenario.id`), captured on opening; a poll that
  moves the screen to a newer hour leaves the table on its own. The heading names it:
  "Run 480 · all 420 aircraft".
- **The data** comes from GET `/api/v1/operational-picture?run=<hour>&view=all` through
  `fetchOperationalPicture`, via a `loadUnfiltered` function `App.tsx` hands to the screen and the
  screen to the panel. Fetched once, not polled. An answer for another hour or under another view is
  refused as a failure; a failure says so with *Try again* and never shows the panel's rows.
- **Columns** are the panel's (shared formatting in `components/em/rowFormat.ts`). Default order:
  out of nominal first, then by identifier; Events oldest first. Every header sorts, a second click
  reverses, `aria-sort` set; an altitude not reported sorts last both ways.
- **Find** narrows by receiver/station, aircraft pseudonym, or source/conclusion, case-insensitive,
  with "n of N shown" and a sentence when nothing matches.
- **Closing**: Escape (stopped there, so the map's Escape does not also fire) or ×; focus returns to
  *View all*; the open tab and the view are unchanged.
- *View all* is disabled with a reason only when there is no hour (no scenario, or the first-paint
  mock's non-numeric id) or no loader (a screen rendered without one, as in panel tests).

### Checked in the browser (dev server, `:1234`)

| Check | Result |
|---|---|
| Run 480, Tracks | "Run 480 · all 420 aircraft" = 17 interrupted + 403 the view hid. |
| Sort | Altitude descending, *not reported* last. |
| Find | "a9" → 17 of 420 shown. |
| Request | `run=480`, `view=all`, on `/api/v1/operational-picture` (checked without printing the URL). Two requests per opening in dev: StrictMode runs the effect twice; the first answer is discarded. |
| Close | Escape closed it; focus on *View all*; Tracks still open; *Anomalous only* still selected. |
| Events | "Run 480 · all 1 conclusion", time column sorted ascending. |

The user confirmed it works.

## Files in flight

None once this handoff is committed.

## Changed

| Commit | Message |
|---|---|
| `3719784` | `spec: amend op-005 -- drill-down tables as an unfiltered overlay over the hour on screen` |
| `d895044` | `test: add tests for op-005` |
| `988c349` | `feat(op-005): drill-down tables over the hour on screen, unfiltered - tests pass` |

**New:**
- `frontend/src/components/em/EmDrillDown.tsx`
- `frontend/src/components/em/rowFormat.ts`, holding the panel's formatters, moved out so both
  components share them.
- `frontend/src/test/drillDown.test.tsx` (30 tests)
- `backend/measurements/mutation/mutate_op005_drilldown.{py,log}`

**Changed:**
- `EmExceptionPanel.tsx`: *View all* is wired; takes `loadUnfiltered`; `PanelData` gains `scenario`.
- `viewVocabulary.ts`: `VIEW_ALL_REASON` is replaced by `NO_HOUR_TO_DRILL` and `DRILL_DOWN_UNWIRED`,
  plus the drill-down words.
- `screens/operationalPicture.tsx`: the `loadUnfiltered` prop.
- `App.tsx`: the `useCallback` loader.
- `exceptionPanel.test.tsx`: one op-004 test re-pointed.
- `mutate_op004_panel.py`: re-pointed, with its log re-run.

**Docs:**
- `CLAUDE.md` repo map.
- `implementation.md` view-filter checklist.
- `measurements/README.md` (two rows).
- `thesis_notes.md`: a new subsection on the drill-down tables.

## Failed attempts

**My own errors:**
- **The visible sort arrow was part of the header text.** It sat in a span inside the header button,
  so each header was named "Time ▲". It is now drawn with CSS `content` and the order is announced by
  `aria-sort`.
- **A find fixture matched two stations.** "VEN" matched Venlo and also Eind*hoven*; now "VENL".
- **Five header queries were page-wide.** They found the panel's table behind the dialog as well, and
  are now scoped to the dialog. This exposed a real property of the build, listed under the open items
  below.
- **The first mutation pass left a survivor:** altitudes compared as text. The fixture's 12,000 / 30,000
  / 35,000 sort the same as text and as numbers. AC-alpha now flies at 9,000 ft and the pass was re-run.
- **The first watcher on the mutation logs exited at once.** It waited for a line the *previous*
  `op-004` log already contained.

**Instrument limits:**
- The browser tool's ref-based clicks did not register on this page; coordinate clicks did.

**Tests changed after implementation (deviations):**
- The five header queries scoped to the dialog.
- The "VENL" fixture.
- The 9,000 ft altitude.

## Next step

1. **Offer the progress-note update.** The drill-down is a small addition to the story: a sentence in
   the screen section, not a figure.
2. **`map-004`**, playback, still gated on `op-008` / `api-008`. Zones appearing and clearing over time
   belong to it.
3. Then, unchanged: `hyp-*`, and `eval-006` (waits on the second rater, mid-October).

Open and unowned:

- **The page behind the drill-down is not inert.** The dialog is `aria-modal`, but a screen reader can
  still reach the panel's table behind it. Fix it (mark the rest of the screen `inert` while it is open)
  or record it as a limitation.
- **The table is not virtualised.** It renders all 420 rows, which was smooth here; a bigger hour has
  not been tried.
- **`diff: false` on the basemap switch is unverified in a browser.** Configure satellite (two
  `VITE_SATELLITE_*` variables in `.env.development.local`), switch, and check the disc survives.
- **Whether "the circle is the area assessed" is read as such** is an evaluation question.
- **The frame-rate figure is one machine and one hour.**
- **Long pseudonymous aircraft names** (`AC-849585568dda`) make wide labels.
- **The frontend is not in Biome's format**, and nothing checks it (`pnpm lint` is lint only).
- **"Tracks (13 interrupted)" / orange aircraft on a quiet hour** may read as an alarm.
- **The evidence panel's sentence for an unexplained conclusion is stale** ("built and not kept").
- **`detection_metrics.py` still imports `save_findings`**, unused.
- **"20.7M observations" is stale** in seven places (the store holds 15.5M).
- **`_corpus.py`'s id ranges are stale**, and **`thesis_notes.md` is misfiled from about line 6900**.
- **A fresh database cannot score batches from the screen** until `BASELINE_QUIET_RUNS` is re-derived
  for it.
