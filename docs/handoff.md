# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session (7–8 October 2026) built **the map**. The user chose zoom 10, a checksum-pinned download
and zones deferred. `map-001` and `map-002` were built and reviewed in the browser. The review asked
for four changes, which became an amendment to `map-001` and `map-003` and a new `map-005`, all
built and reviewed:
- a light basemap;
- no grey edge;
- real icons, coloured by state;
- a pop-up and labels.

Every item followed spec → failing tests → code → browser review → `passes: true`, committed on
`main`.

## Current state

Backlog **95 of 119** (91 of 118 at the start; `map-005` was added). Tree clean once this handoff and
the progress note are committed; `main` in sync with `origin/main`.

- Backend: **2117 passed, 99.93% coverage** (5571 statements, 4 missed; 2107 at the start), ruff, Black and mypy clean on what changed.
- Frontend: **353 passed** (298 at the start), locally and in the `frontend-test` container; Biome lint
  and `tsc -b` clean.
- Mutation: `mutate_map001_view.log` **47 of 47** (covers `map-001`, `map-002`, `map-003`, `map-005`).

### What the map does now

- **Basemap** (`map-001`):
  - Protomaps **light** flavour from build 20261006, served from this origin.
  - Two archives: the corpus box (3–11°E, 49–54°N) to zoom 10, and a Europe overview
    (-11–30°E, 35–61°N) to zoom 6 drawn under it at every zoom. The box's source starts at zoom 7, it
    has no background layer of its own, and the overview's labels stop at zoom 7.
  - The camera's `maxBounds` is the overview box.
  - `make basemap` fetches 775 files (92 MB) in Docker, verifies every SHA-256 against
    `frontend/public/basemap/manifest.json`, and installs only if all match.
  - Satellite is opt-in through two env variables; nothing in the repo names a provider.
- **Three non-map states** (`map-002`): not configured; archive unreadable (names `make basemap`);
  library failed to start.
- **Markers** (`map-001` (12), `map-003`):
  - HTML buttons with an accessible name like "Aircraft AC-1, interrupted".
  - Colours: orange for anomalous (fault / deviating / interrupted), dark blue for nominal aircraft,
    dark teal for nominal receivers, grey hollow for unexamined (named "not examined").
  - Stacked by importance, so an anomalous receiver draws on top.
- **Pop-up and labels** (`map-005`):
  - One pop-up, payload fields only. Escape, ×, or a map click closes it; it closes if the entity
    leaves the payload.
  - Receivers labelled with their station; interrupted aircraft with name · altitude; all aircraft
    from zoom 9.
  - Labels are placed greedily by rank and avoid other labels and the icons of entities at least as
    important.

### Measured this session

| Measurement | Result |
|---|---|
| Basemap dry-run sizes, box at z9 / z10 / z11 / z12 | 27 / 86 / 219 / 529 MB |
| Wider z10 cut, +2° / +3° / +5° each side | 147 / 214 / 324 MB |
| Europe overview (-11..30E, 35..61N) at z6 / z7 / z8 | 6.2 / 33 / 118 MB |
| `make basemap` | ~15 s; second run byte-identical (box `a0e7eeec…46eb`, 85,630,679 B; overview 6,201,154 B) |
| Corrupted checksum in a manifest copy | names the file, installs nothing, existing set untouched |
| Panning under *All* (427 markers), user's Mac, Chrome, dev server | 912 frames / 8 s, median 8 ms, p90 9, p99 9, one > 50 ms |
| Production build, other-origin requests | none (two `data:` URIs from MapLibre's CSS) |
| Run 480 (ambiguous-mixed-evidence) on screen | RF-01 Schiphol `fault`, conclusion at 12:38:51 = staged onset; 17 interrupted aircraft (22 gaps); 420 aircraft, 403 nominal |

## Files in flight

None once this handoff and the progress note are committed. `frontend/public/basemap/` holds the
downloaded (gitignored) archives; a fresh clone needs `make basemap`.

## Changed

| Commit | Message |
|---|---|
| `9f1ba8d` | `spec: amend map-001, map-002 -- zoom-10 Protomaps cut by checksum, self-hosted assets, three non-map states` |
| `f761e5c` | `test: add tests for map-001, map-002` |
| `82202f8` | `spec: amend map-001, map-003; add map-005 -- light basemap, Europe overview, markers, pop-up and labels` |
| `a18f8a9` | `test: add tests for map-001, map-003, map-005` |
| `bac8ac3` | `feat(map-001, map-002, map-003, map-005): offline light map with Europe overview, state markers, pop-up and labels - tests pass` |

**New:**
- `frontend/src/components/map/MapView.tsx`, the only importer of `maplibre-gl`, `pmtiles` and
  `@protomaps/basemaps`.
- `frontend/public/basemap/manifest.json`.
- `frontend/.env.development` and `.env.production` (`VITE_BASEMAP_ARCHIVE`).
- Tests: `mapView.test.tsx`, `mapBoundary.test.tsx`, `nodeFs.d.ts`.
- `measurements/mutation/mutate_map001_view.*`.
- Dependencies: `maplibre-gl` 6.13, `pmtiles` 4.5, `@protomaps/basemaps` 5.7.

**Changed:**
- `Makefile` (`basemap` target, pinned `go-pmtiles:v1.31.2` and `alpine:3.20`).
- `.gitignore` (basemap files and the committed `.env` exceptions).
- `frontend/nginx.conf` (`.mjs` served as `text/javascript`).
- The screen (renders `MapView`).
- `test/setup.ts` stub.
- `exceptionPanel.test.tsx` re-pointed.
- `test_ops_command_surface.py` (+10).

**Docs:**
- `CLAUDE.md` repo map, `README.md` (`make basemap`), `implementation.md` Phase 4,
  `measurements/README.md`.
- `qa.md` §154 (pop-ups and labels were unspecced).
- `thesis_notes.md`: two subsections on the checksum download and browser-only faults, and on the
  light / overview / markers round. The MapView diff-size gap is filled.
- `progress_note.html`: a new section with three screenshots of run 480.

## Failed attempts

**Three faults passed every unit test and showed a blank map in the browser:**
- MapLibre 6 derives its worker URL from its own file location, which Vite's dependency bundling
  moves. Fixed with `setWorkerUrl` and a `?url` import.
- MapLibre refuses a relative sprite URL. The error was silent because listening for `error` stops
  MapLibre logging. Fixed by making the sprite absolute on this origin and re-logging non-satellite
  errors.
- nginx served `.mjs` as `application/octet-stream`, so the module worker was refused. Fixed with a
  `location ~ \.mjs$` block. The browser had cached the old type, so a `cache: 'reload'` fetch was
  needed before the fix showed.

Each fix got a test after the code.

**The committed boundary test could not read `.env` files.** Vite's `server.fs.deny` blocks them,
and `new URL(…, import.meta.url)` is rewritten into an asset import. Changed to `readFileSync`
relative to the Vitest root, with a narrow `node:fs` declaration instead of adding Node types.

**The boundary test's filter missed test files.** `import.meta.glob` lists them as `./x.test.tsx`,
not `/test/`, so it failed when `mapView.test.tsx` imported `@protomaps/basemaps`. The filter was
fixed after the test commit.

**Tests written or changed after implementation (deviations):**
- the worker-URL, absolute-sprite and nginx tests;
- the satellite-start tightening (round-one mutation survivor);
- the label-avoids-icon test, added when the browser showed labels across a cluster's icons, which
  goes beyond the spec's wording;
- the reordered collision test and the reopen test (round-two mutation survivors).

One mutant (a new marker placed latitude first) was removed as equivalent: the next render
re-places it.

**I could not measure frame rate myself.** The automation tab is backgrounded
(`visibilityState: hidden`) and Chrome runs no rAF there, so the user ran the logger.

**First-round dark basemap and dots were rejected on review** for the grey edge, readability, a light
map preferred, and nothing on click. The reversal is recorded in the thesis notes.

## Next step

1. **`op-005`**, the drill-down tables. The panel's *View all* is still disabled waiting on them.
2. **Interference zones**: a new API item first (the payload has no zone shape), then the map.
3. **`map-004`**, playback, still gated on `op-008` / `api-008`.
4. Then, unchanged: `hyp-*`, and `eval-006` (waits on the second rater, mid-October).

Open and unowned:

- **The frame-rate figure is one machine and one hour.** Re-measure on slower hardware before
  claiming it generally.
- **Long pseudonymous aircraft names** (`AC-849585568dda`) make wide labels. They are payload names,
  shown as sent.
- **The frontend is not in Biome's format** and nothing checks it (`pnpm lint` is lint only).
- **"Tracks (13 interrupted)" / orange aircraft on a quiet hour** may read as an alarm. Flagged for
  the evaluation in the progress note and thesis notes.
- **The evidence panel's sentence for an unexplained conclusion is stale** ("built and not kept").
- **`detection_metrics.py` still imports `save_findings`**, unused.
- **"20.7M observations" is stale** in seven places (the store holds 15.5M).
- **`_corpus.py`'s id ranges are stale**; **`thesis_notes.md` is misfiled from about line 6900**.
- **A fresh database cannot score batches from the screen** until `BASELINE_QUIET_RUNS` is re-derived
  for it.
