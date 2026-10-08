# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session (8 October 2026) put **interference zones on the map** and fixed the pop-up after review:
- `api-017`: the picture serves each stored interference claim as a zone, with the radius recorded with
  it;
- `map-006`: the map draws the assessed disc, a centre marker, a label and a pop-up;
- `map-005` amended: the pop-up opens inside the map and can be moved.

The user chose the assessed disc over an evidence footprint or receivers only, and a separate API item
before the map item. Review then asked for two changes: a zone colour distinct from the markers, and a
movable pop-up. Every item followed spec → failing tests → code → browser review → `passes: true`,
committed on `main`.

## Current state

Backlog **97 of 121** (95 of 119 at the start; `api-017` and `map-006` were added and built). Tree clean
once this handoff is committed; `main` in sync with `origin/main`.

- Backend: **2134 passed, 99.93% coverage** (5611 statements, 4 missed; 2117 at the start); ruff, Black
  and mypy clean on what changed.
- Frontend: **378 passed** (353 at the start); Biome lint and `tsc -b` clean.
- Mutation:

  | Log | Result | Covers |
  |---|---|---|
  | `mutate_map001_view.log` | **47 of 47** (re-run with zones in place) | `map-001`, `map-002`, `map-003`, `map-005` (1)–(2) |
  | `mutate_map006_zones.log` | **26 of 26** | `map-006` |
  | `mutate_map005_popup.log` | **10 of 10** | `map-005` (3) |

### What zones do now

- **Server (`api-017`):**
  - `interferenceZones` on GET `/api/v1/operational-picture`, one per stored `FUSION-SPATIAL`
    `possible_interference_zone`.
  - Each zone's `id` equals its timeline event's id.
  - `radiusKm` comes from the policy stored with the row (`interference_radii_for_run` in
    `app/db/findings.py`), null when none was stored, never a default.
  - `confidence` is a Level; `corroboration` is sent verbatim.
  - Filtered like events: *Nominal only* withholds them and counts them in
    `view.suppressed.interferenceZones`. An unexamined run has none.
  - All 100 stored interference rows carry `confidence`, `corroboration` and the radius setting (checked
    in the store).
- **Map (`map-006`):**
  - A dashed geodesic disc of the assessed radius, with a faint fill, in DESIGN.md's error-container red
    `#93000a`, a colour no marker uses.
  - The disc is redrawn on every `style.load` and updated with `setData` when the zones change.
  - The disc binds no handlers.
  - The basemap switch passes `diff: false`.
  - Centre marker named "Interference zone over A and B, Medium confidence".
  - Label "Possible interference · Medium", ranked above every other label.
  - The pop-up shows receivers, window (UTC), confidence, the corroboration sentence
    (`CORROBORATION_COPY` in `detectionVocabulary.ts`) and the centre. It always ends with the sentence
    that the circle is the area assessed, not an extent. With no radius, there is no circle and the
    pop-up says so.
- **Pop-up (`map-005` (3)):**
  - Opens above its marker, then below, then beside it (right, then left), pulled in from the edges.
  - Moved by dragging its header or with the arrow keys (16 px).
  - Keeps its offset from the marker on a pan; at least 40 px stays inside the map.
  - Resets when closed, reopened or replaced.

### Checked in the browser (dev server, `:1234`)

| Hour | Result |
|---|---|
| Run 420 | One zone over RF-04 (Eindhoven) and RF-05 (Weeze), Medium, not measurable, centre 51.5262°N 5.7584°E, 60 km. Gone under *Nominal only* (marker and disc), back under *Anomalous only*. |
| Run 411 | The pop-up opens beside the zone marker when it fits neither above nor below. The user confirmed a real drag and a pan both work. |

## Files in flight

None once this handoff is committed.

## Changed

| Commit | Message |
|---|---|
| `0e752cf` | `spec: add api-017, map-006 -- interference zones served from the store and drawn as the disc assessed` |
| `a5523a6` | `test: add tests for api-017, map-006` |
| `62fba71` | `feat(api-017, map-006): interference zones served with their recorded radius and drawn as the assessed disc - tests pass` |
| `ea09d32` | `spec: amend map-005 -- pop-up fits inside the map and can be moved` |
| `410b7bc` | `test: add tests for map-005 (3) -- pop-up placement and moving` |
| `b31c8d0` | `feat(map-005): pop-up opens inside the map and can be moved - tests pass` |

**New:**
- `measurements/mutation/mutate_map006_zones.*` and `mutate_map005_popup.*`. Their mutants may make
  several edits.

**Changed:**
- **Backend:**
  - `app/db/findings.py` (`interference_radii_for_run`).
  - `app/api/v1/schemas/operational_picture.py` (`ZoneCentre`, `InterferenceZone`, `Corroboration`,
    `_zones`, `_event_id`, `_ordered`, `_corroboration`).
  - `app/api/v1/operational_picture.py` (passes `zone_radii`).
- **Frontend:**
  - `types/operationalPicture.ts` and the mock.
  - `lib/detectionVocabulary.ts` (`CORROBORATION_COPY`).
  - The screen (passes `zones`).
  - `components/map/MapView.tsx` (`zoneOutline`, zone source and layers, zone entity, pop-up
    placement and moving).
- **Tests:** `test_api_operational_picture.py`, `mapView.test.tsx`, `mapBoundary.test.tsx`;
  `exceptionPanel.test.tsx` and `viewFilter.test.tsx` (fixtures only).
- **Measurements:** `mutate_map001_view.py` (one anchor re-pointed).

**Docs:**
- `CLAUDE.md` repo map.
- `implementation.md` Phase 4.
- `measurements/README.md` (two rows).
- `qa.md` §155 (the pop-up question, with the fitting-versus-moving distinction in the glossary).
- `thesis_notes.md`: two subsections, one on zones drawn as the assessed disc (including the colour
  reversal), one on the pop-up learning the map's edges.

## Failed attempts

**My own errors:**
- **I claimed `app/db/findings.py` could import `app.detection.fusion` at module level.** I checked
  only direct imports. `fusion` reaches `db.findings` through `rate_excess.findings_near`, so collection
  failed on a cycle. The import now sits inside the function, with a comment.
- **I named the window formatter `window`, shadowing the global.** `onThisOrigin` read
  `window.location` from my function, threw inside the map's start-up `try`, and 37 tests reported
  "could not start the map". The blanket catch turns any bug into the WebGL message.
- **I first drew the zone in the anomalous orange,** reasoning that a zone is an anomalous finding. In
  review it read as part of the orange markers inside it, and the user asked for a different colour.
  Recorded as a reversal in the thesis notes.
- **I chose a clamp for a pop-up that fits neither above nor below.** It covered the marker it
  described (seen on run 411); now it opens beside the marker. The spec was widened after the code.
- **One mutation run was wasted** by a `sed` anchor that silently did not match. Python replacements
  that assert a count of 1 replaced it.

**Faults the tests could not see:**
- **MapLibre's `setStyle` diffs by default.** A successful diff fires no `style.load` and drops sources
  the new style lacks, so the disc would vanish on a basemap switch. The switch now passes
  `diff: false`. Found by reading MapLibre's source. **Unverified in a browser:** satellite is not
  configured locally.
- **`setPointerCapture` throws for a pointer the browser does not consider active**, which cancelled
  the drag before its listeners were attached. Now guarded.
- **The first zone mutation pass left a stale-disc survivor:** a disc never updated when the zones
  changed. The test double's `getSource` returned nothing, so the update path never ran. The double now
  keeps its sources until `setStyle`, and a test asserts the disc empties.

**Instrument limits:**
- The automation tool's drag sends no pointer-down, so a real drag could not be done through it. The
  drag was exercised by dispatching pointer events in the page, and the user confirmed it by hand.
- The automation tab is hidden, so Chrome runs no animation frames and pan-following could not be
  watched (the same limit as the frame-rate measurement).

**Tests written or changed after implementation (deviations):**
- The stale-disc test and the stand-in map change.
- The unrecognised-corroboration refusal test (proved against a mutant).
- The zone-colour test (written before the colour change, after the zone code).
- The beside-the-marker test (proved against the old fallback).
- The `corroboration` added to the existing `_zone` fixture: it lacked a field every stored row has.
- `interferenceZones: 0` added to ten frontend fixtures. `tsc -b` caught them; Vitest does not
  type-check.

## Next step

1. **Offer the progress-note update.** Zones are the conclusion the map exists to show, and run 420 or
   411 would carry it.
2. **`op-005`**, the drill-down tables. The panel's *View all* is still disabled waiting on them.
3. **`map-004`**, playback, still gated on `op-008` / `api-008`. Zones appearing and clearing over time
   belongs to it.
4. Then, unchanged: `hyp-*`, and `eval-006` (waits on the second rater, mid-October).

Open and unowned:

- **`diff: false` on the basemap switch is unverified in a browser.** Configure satellite (two
  `VITE_SATELLITE_*` variables in `.env.development.local`), switch, and check the disc survives.
- **Whether "the circle is the area assessed" is read as such** is an evaluation question. A tidy
  circle invites reading it as a footprint.
- **The frame-rate figure is one machine and one hour.** Re-measure on slower hardware before
  claiming it generally.
- **Long pseudonymous aircraft names** (`AC-849585568dda`) make wide labels.
- **The frontend is not in Biome's format** and nothing checks it (`pnpm lint` is lint only).
- **"Tracks (13 interrupted)" / orange aircraft on a quiet hour** may read as an alarm.
- **The evidence panel's sentence for an unexplained conclusion is stale** ("built and not kept").
- **`detection_metrics.py` still imports `save_findings`**, unused.
- **"20.7M observations" is stale** in seven places (the store holds 15.5M).
- **`_corpus.py`'s id ranges are stale**; **`thesis_notes.md` is misfiled from about line 6900**.
- **A fresh database cannot score batches from the screen** until `BASELINE_QUIET_RUNS` is re-derived
  for it.
