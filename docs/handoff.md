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

The session then scoped **the Hypotheses screen** against the design reference and the store
(`qa.md` §157). The user settled five decisions and then **parked the feature**: they are about to score
the blind evaluation pack, and the screen would name the generator of the very explanations being
scored. Nothing about it is specified or built yet; the decisions are under Next step.

While the user scores, the session started **playback** and built **`api-008`**, the time-windowed
track query: every aircraft's positions over a span of at most 300 s, filtered by the view, with the
stored gaps. The spec was amended before tests on measuring the store, and the user reviewed it against
real figures for run 480. Then **`op-008`**, the playback transport: play, pause, speed and scrub over
the hour's simulated window, producing a cursor the map is handed (and ignores until `map-004`). Review
changed one thing: the bar now pushes the exception panel down instead of shrinking the map. Then
**`map-004`**: the map follows the cursor (aircraft, trails with stored gaps broken, zones in their
window). Review found that broken segments were missing for most gaps, which exposed a second gap
mechanism (frozen) the first build ignored; fixed by amending the spec and the code. Two items were
then specified for receiver states over time (`api-018`, `map-007`).

## Current state

Backlog **101 of 123** (97 of 121 at the start; `api-018` and `map-007` added). Tree clean once this handoff is committed; `main` in sync
with `origin/main`.

- Backend: **2179 passed** (2134 at the start: 40 `api-008` tests, 4 parametrised parity cases, and
  one empty-run test). Ruff, Black and mypy are clean on what changed. `playback.py` has 100% coverage,
  and both new repository reads are covered.
- Frontend: **472 passed** (378 at the start; 30 `op-005`, 24 `op-008`, 40 `map-004`); Biome lint and
  `tsc -b` clean.
- Mutation:

  | Log | Result | Covers |
  |---|---|---|
  | `mutate_map001_view.log`, `mutate_map006_zones.log` | **47 of 47**, **26 of 26** (re-run; five anchors re-pointed after the `MarkerButton` refactor and the screen's `mapTracks`/`mapZones`) | `map-001`, `map-005`, `map-006` |
  | `mutate_map004_playback.log` | **35 of 35** (second run; first 32 of 35) | `map-004` |
  | `mutate_op008_playback.log` | **25 of 26** (second run; first 24 of 27). The survivor, an unclamped seek, is equivalent at the UI | `op-008` |
  | `mutate_op005_drilldown.log` | **31 of 31 (second run; first 30 of 31)** | `op-005` |
  | `mutate_op004_panel.log` | **20 of 20** (re-run; one mutant retired, three anchors re-pointed) | `op-004` |

### What the map does during playback now (`map-004`)

- **Pure arithmetic in `lib/trackPlayback.ts`:**
  - `playbackTracks`: interpolate between reports ≤ 20 s apart; otherwise hold at the last report,
    marked `stale` once 20 s have passed; not drawn before the first report; removed 60 s after the
    last unless a stored gap covers the cursor. In an unloaded span it holds at the last known
    position, marked, unless the loaded data shows the aircraft had already left.
  - `trailsAt`: the last 120 s. A hole crossing a stored gap is one broken segment; any other hole
    breaks the trail and is not drawn.
  - `zonesAt`, `spansToLoad` (300 s spans aligned to the window's start), `mergeWindow`.
  - **The stored gap is the authority**: reports strictly inside a stored gap are set aside, so a
    frozen gap (rows arriving with a repeated stale fix) is a gap.
- **`useTrackBuffer`:**
  - loads the span holding the cursor and the next, under `selected`, each once;
  - keeps what has loaded;
  - resets on a new run, view or window;
  - takes the loader from `App.tsx` (`fetchTracks` in `lib/api.ts`).
- **The screen** hands the map `playbackTracks`, `zonesAt` and `trailsAt` while open, and the picture's
  own rows when closed.
- **`MapView`:**
  - a `trails` source with a muted solid layer and a dashed `#ffb4ab` broken layer, filtered on
    `broken`, redrawn on `style.load`, with no handlers bound;
  - "Aircraft …, not reporting" for a held aircraft, which is drawn faded;
  - marker buttons memoised in `MarkerButton`.
- **Run 480, measured:**
  - 22 stored gaps: 17 frozen, 5 holes. Broken segments appear at 69 of 91 ten-second moments, the
    first at 220 s; 16 aircraft.
  - Between 9 and 20 aircraft are not reporting at any moment.
  - *Anomalous only*: 19 aircraft at 12:41:51, 4 not reporting.
  - Three span requests on open plus a scrub, with no duplicates under StrictMode.
- **Performance (dev build, one synchronous cursor update, about 360 aircraft under *All*):**
  - about 34 ms before memoising the markers, **about 25 ms after** (90th percentile 31–35 ms);
  - the pure work is 0.3 ms (positions, 518 aircraft, 33,273 reports) and 1.3 ms (trails);
  - no redraw throttle added;
  - production is not measured.
- **The user confirmed it works**, including the broken segments after the fix.

### What the playback transport does now (`op-008`)

- **Off by default.** *Play back this hour* sits in the map's bottom-left corner. It is disabled with
  "This hour has no recorded window to play back." when the hours index gives no valid window for the
  hour.
- **Opening:**
  - takes the window from the hours index (`observedFrom`/`observedTo`; all 460 hours have one);
  - **pins the hour** (calls `onSelectHour` unless it is already pinned);
  - opens the bar under the map with the cursor at the start, paused, at 1×.
- **Playing:**
  - `usePlayback` runs a `requestAnimationFrame` loop timed with `performance.now()`;
  - each frame's interval is capped at `MAX_FRAME_MS = 250`, so a hidden tab does not leap;
  - the cursor is clamped to the window, and reaching the end pauses there; play from the end restarts.
- **The bar (`EmPlaybackBar`):**
  - Play/Pause and the speeds 1×/4×/16×/60×;
  - a native range slider (`step` 10 s, `aria-valuetext` the clock), whose thumb snaps to 10 s while
    the cursor itself does not;
  - "12:41:20 UTC · 4:29 of 15:00";
  - *Close playback*, which leaves the hour pinned.
- **Hour changes:** another hour on screen closes playback.
- **The map** gets `cursor` (ISO, or null when closed). `MapView` declares the prop and does not read it
  yet.
- **Layout (amended on review):** the screen measures the bar with a `ResizeObserver` and adds its
  height plus the 16 px gap to the one-window page through `--playback-extra`. Measured on run 480: the
  map is 486 px closed and open, and the panel moves down 60 px (a 44 px bar and a 16 px gap). jsdom
  cannot see layout, so this rests on that measurement.
- **Checked in the browser:**
  - opening pinned run 480;
  - 60× advanced, in ≤15 s steps per forced frame (the hidden tab);
  - End then Left Left gave 12:51:31 · 14:40 of 15:00;
  - close restored the button.

  **The user confirmed it works.**

### What the tracks endpoint does now (`api-008`)

- **Request:** GET `/api/v1/operational-picture/tracks?run=<id>&from=<iso>&to=<iso>&view=<view>`.
  `run`, `from` and `to` are required; a missing `view` means all.
- **The span:**
  - Half-open, and at most `MAX_SPAN_SECONDS = 300`.
  - It must run forwards and carry a timezone, or the request gets a 422 naming the bound.
  - It is checked before any read, and refused rather than truncated.
- **Errors and empties:** an unknown run is a 404 naming it; a span outside the run is a 200 with no
  aircraft.
- **Response (`PlaybackWindow`):**
  - `runId`, `recordedFrom` and `recordedTo` (the run's first and last position, or null);
  - `servedFrom` and `servedTo` (exactly what was asked);
  - `view`, `examined` and `withheld`.
- **Per aircraft:**
  - `id`, `name` and `state` from the picture's own `_track`;
  - positions oldest first, with altitude in feet or null;
  - `gaps`: the stored `TRACK-GAP` findings overlapping the span, oldest first; `[]` when examined and
    none overlap; `null` when unexamined.
- **Code:**
  - `app/api/v1/schemas/playback.py` is pure, and imports the picture's `_track`, `_interrupted`,
    `_admit`, `_feet` and `_of`, so there is one definition of each.
  - `app/db/repository.py` gains `track_positions_between` (ordered by aircraft, then time) and
    `track_window`.
  - The four `Playback*` shapes are in `types/operationalPicture.ts`, parity-checked.
- **Measured on the running backend, run 480, 12:37–12:42:**

  | View | Aircraft | Positions | Size | Time |
  |---|---|---|---|---|
  | All | 413 | 10,974 | 1.13 MB | ≈0.45 s |
  | *Anomalous only* | 19 (394 withheld), 15 gaps | 472 | 50 KB | ≈0.45 s |

  The run's recorded window is 12:37:00–12:51:50. A run holds about 33,000 positions from about 520
  aircraft at an exact 10 s cadence, about 3 MB as JSON in total.

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

### What the store holds for the Hypotheses screen (read 9 October 2026)

- **155 hypotheses over 20 bundles**, one bundle in each of runs 102–175: 10 `FUSION-SPATIAL`
  interference and 10 `SENSOR-FAULT` conclusions.
- **Per bundle:** 5–6 hosted rows (`gpt-4.1-2025-04-14`, temperature 0, seed 20260925, titles differing
  between samples) and 2 template rows.
- **State:** every `grounding_passed` is true, every status `New`, and `analyst_feedback` is empty.
- **No timestamp column** on `hypotheses`, so order is by id.
- The picture serves `hypotheses: []` for every hour, so the rail always reads *No active hypotheses*.

## Files in flight

None once this handoff is committed.

## Changed

| Commit | Message |
|---|---|
| `3719784` | `spec: amend op-005 -- drill-down tables as an unfiltered overlay over the hour on screen` |
| `d895044` | `test: add tests for op-005` |
| `988c349` | `feat(op-005): drill-down tables over the hour on screen, unfiltered - tests pass` |
| `a9acda4` | `spec: amend api-008 -- time-windowed tracks, bounded, filtered by view, with stored gaps` |
| `0918211` | `test: add tests for api-008` |
| `6c3bc2f` | `feat(api-008): time-windowed track query for playback - tests pass` |
| `2591ea5` | `docs: handoff for api-008` |
| `35d38d1` | `spec: amend op-008 -- playback transport over the hour's simulated window` |
| `5c1f610` | `test: add tests for op-008` |
| `209a883` | `spec: amend op-008 -- the bar pushes the panel down, the map keeps its height` |
| `6ed02e9` | `feat(op-008): playback transport over the hour's simulated window - tests pass` |
| `005caf0` | `docs: handoff for op-008` |
| `237590a` | `spec: amend map-004 -- playback positions, holes, trails and zones from the cursor alone` |
| `ac92306` | `test: add tests for map-004` |
| `4c1ed22` | `spec: amend map-004 -- a frozen gap is a gap; the stored gap is the authority` |
| `c0a48d6` | `test: add tests for map-004 frozen gaps` |
| `6a7fa73` | `feat(map-004): the map follows the playback cursor - tests pass` |
| `403295c` | `spec: add api-018, map-007 -- receiver states over the hour, drawn at the cursor` |
| `503860c` | `docs: handoff for the drill-down tables` |
| `8a03d0c` | `docs: progress note covers the drill-down tables` (published to the same page, version 7) |
| `603eae7` | `docs: qa 156 -- what comes next` |
| `e56d16d` | `docs: qa 157 -- the hypothesis design against the stored data` |

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

- **An `api-008` test passed before the endpoint existed.** The unknown-run test expected a 404, and
  a missing route is also a 404. It now asserts that the detail names run 999.
- **I wrote a test that could not fail** (that the fixtures are a 2022 hour) and removed it before
  committing.
- **I named `usePlayback`'s parameter `window` again**, the same shadowing that broke 37 map tests last
  session. I caught it before running anything, and a regex rename then missed three dependency
  lists and rewrote a user-facing sentence ("recorded span"). Both were fixed before the tests ran.
- **My first `op-008` test put the frame cap inside `advance`**, so `advance(START, 1000, 4)` would have
  been capped at 250 ms. The cap became its own `frameInterval`.
- **A missing module fails a whole Vitest file at load**, which would have hidden a screen test passing
  for the wrong reason. The test looks `lib/playback.ts` up with `import.meta.glob`, so each test failed
  on its own.
- **I first laid the bar out inside the one-window layout**, so opening it shrank the map. The user asked
  for the panel to move instead (`qa.md` §158). The spec was amended after the code.
- **I built `map-004`'s broken segments for one of the gap rule's two mechanisms.** `anom-010`'s own
  module documents both (rows that stop; rows that keep arriving with a frozen, stale position), and
  my fixture had only the first. On run 480, 17 of 22 gaps are frozen, so the user saw no red
  segments. Found in review (`qa.md` §159); the spec was amended, failing tests were committed, then
  the fix.
- **I ran `biome format --write src` over the whole frontend**, which reformatted about 25 files
  outside the item. I reverted them, then split the remaining diff into minimal hunks and
  reverse-applied the 16 that were formatting only. The frontend is still not in Biome's format;
  never format the tree wholesale.
- **I named callback parameters `window` twice more** in `map-004` (`useTrackBuffer`, `mergeWindow`),
  and caught both before running.
- **Timing loops in the hidden tab:** waits between iterations are throttled to about 1 s, so a 40-step
  loop overran the tool's 45 s limit, and loops with waits gave inflated, non-comparable figures
  (40–60 ms). The comparable method is a tight synchronous loop with no waits.
- **My handoff edit assumed a placeholder I had already replaced.** Its assertion stopped the edit,
  but the git commands followed on a new line rather than after `&&`, so they ran anyway and made the
  `op-008` feature commit without the handoff. The feature commit is complete; the handoff followed
  separately.

**Tests changed after implementation (deviations):**
- `op-005`:
  - The five header queries scoped to the dialog.
  - The "VENL" fixture.
  - The 9,000 ft altitude.
- `api-008`:
  - The four `Playback*` shapes registered in `test_api_operational_picture.py`'s `MODELS`. Its parser
    check requires every interface in the contract to have a model.
  - The empty-run database test, added when coverage showed `track_window`'s empty branch untested.
    Removing the branch's guard is equivalent at the API, since both serve nulls; the test pins the
    behaviour, not the guard.
- `map-004`:
  - The test helper's loader type, fixed when `tsc -b` failed (Vitest does not type-check).
  - The frozen-gap tests followed a spec amendment made after the first implementation. They were
    committed failing before the fix.
  - Three tests written after the first mutation pass, one per survivor:
    - a merge with the later span first;
    - the trails' `addSource` counted after a basemap switch;
    - `fetchTracks`' URL and its two refusals.
- `op-008`:
  - Two tests written after the first mutation pass: an inverted window disables the button, and a
    seek past the end holds at the end.
  - The map stand-in in `setup.ts` now prints the cursor. That was written with the tests, not after.
  - The layout change has no test (jsdom has no layout); the browser measurement above is the evidence.

## Next step

**The user is scoring the blind pack now. Do not start the Hypotheses screen until they say scoring is
done**, and while they score, do not print, open or summarise anything that links an explanation to its
arm (the arm key, `campaign_arms.csv`, generator columns of the campaign rows).

1. **`eval-006` scoring** (the user, now; the second rater from mid-October).
2. **The Hypotheses screen, once the user's scoring is done.** Decided 9 October 2026 (`qa.md` §157):
   - **Option A, one explanation per conclusion.** The analyst's queue is the 20 conclusions that have
     hypotheses, one explanation each, never the campaign's 5–6 hosted samples and 2 template copies.
     Rejected: B (a read-only template tab beside the AI, which invites anchoring on agreement) and
     C (both side by side with a verdict each, which makes the workbench an arm-comparison tool; that
     is the blind scoring's job).
   - **"The" explanation is the pack's row**: the generation at `SCORED_ORDINAL` for the bundle and the
     requested arm, as `_scored_generations` in `app/evaluation/pack.py` takes it, so verdicts and blind
     scores refer to the same text. For the AI-arm explanation that is the hosted request's scored row.
   - **Provenance is always shown** (`ai-010`): the generator and model on every explanation, and a
     fallback (`requested_generator` hosted, `generator` template) styled as degraded, not as a neutral
     label. None is stored yet, so it needs a fixture.
   - **Verdict → status** (fills the gap `api-005` leaves): confirm → Confirmed; reject → Rejected;
     false positive → Rejected with the verdict kept on the feedback row; needs more evidence →
     Under review. *Inconclusive* stays in the stored set and is unused.
   - **A hypothesis gets its own address**, `#hypotheses/<id>`, as a small `nav-*` item, because
     `screenFromHash` reads bare screen ids; the cards on the Operational Picture (`op-002`) link to it.
   - **Against the design reference** (`assets/Design/Hypothesis_analysis_v2/`), which predates the
     layer:
     - *Keep:* the title, confidence pips, status (`New` reworded), window, verdict buttons and note,
       and the disclaimer.
     - *Drop:* the invented sources (SIGINT, LEO-SAT, solar flux, maintenance), categories on
       uncertainty cards, "Sector A / Zone AZ-402", the satellite heat map, and the live-feed chrome.
     - *Split:* uncertainty and alternatives into two sections (`hyp-003`).
     - *Add:* summary, recommended action, provenance, a list to choose from, verdict history, a
       not-found state, and a map of the conclusion's zone or receiver through `MapView`.
   - **Spec work, in order:**
     - amend `api-004`: join each hypothesis to its bundle (run, window, centre, receivers, rule), apply
       the selection above, re-run `ai-008` per citation on read, and return verdict history;
     - add an item for the picture to serve the hour's explanations, since it serves `hypotheses: []` today;
     - amend `hyp-001`–`hyp-003` to the keep, drop and add lists above;
     - pin the verdict mapping in `api-005`;
     - add the `nav-*` address item.

     Then build from `api-004` and the list.
3. **While the screen is parked**, the next items touch no hypothesis data:
   - **`api-018`**: receiver states over an hour, served as intervals per receiver joined from
     stored findings (fault; deviating from noise deviations or an interference claim naming it),
     worst first; null on an unexamined hour.
   - **Then `map-007`**: receivers in their state at the playback cursor.

   Both were specified this session at the user's request and are agreed.
4. **Offer the progress-note update.** Playback is now visible: the controls, aircraft moving with
   trails, and broken segments where reporting stopped, all on run 480.

Open and unowned:

- **Playback under *All* costs about 25 ms per update in the dev build**, over a 16 ms frame. The
  frame rate degrades gracefully, but production is unmeasured and no throttle exists.
- **During playback the exception panel still shows the whole hour.** That is by design, but a
  reader could expect it to follow the cursor.
- **Closing playback leaves the hour pinned.** The spec does not ask for unpinning, and *Follow the
  newest* is beside it; whether analysts expect closing to unpin is unasked.
- **The page behind the drill-down is not inert.** The dialog is `aria-modal`, but a screen reader can
  still reach the panel's table behind it. Fix it (mark the rest of the screen `inert` while it is open)
  or record it as a limitation.
- **The backend does not compress responses.** `api-008`'s five-minute span under *All* is 1.13 MB on
  the wire; gzip (FastAPI's middleware, or nginx in the container) would cut it substantially.
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
