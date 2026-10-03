# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

Three things this session, in the order the user asked for them.

1. **The basemap decision was taken** — default basemap offline, satellite a documented opt-in that
   needs network. This had been blocking `map-001` since the previous session.
2. **The progress note was brought current** — the re-score, the schema-drift story, and three
   stale counts.
3. **`api-013` and `op-009`: the screen can be asked for a particular hour.** The first item of the
   agreed five-item screen sequence, and the one that gates looking at the other four.

## Current state

Backlog **76 of 110** (`api-013` and `op-009` are new; `map-001` and `map-002` amended and still
unbuilt).

- Backend: **1945 passed, 99.92% coverage, exit 0**, in containers (1931 mid-session, before the
  mutation pass forced two tests out; 1895 at the start).
- Frontend: **107 passed**, Biome lint clean, `tsc -b` clean. No coverage tooling exists on that
  side, which is why `op-009` has a mutation pass instead.
- `make lint`, `make format` and mypy clean (79 source files).
- At **100%**: `app/api/v1/operational_picture.py` (20 statements),
  `app/api/v1/schemas/operational_picture.py` (164), `app/dal/models.py` (85). The new
  `selectable_hours` lines in `app/db/repository.py` are covered.
- Mutation: **23 of 23 killed across both suites, no survivors, none declared equivalent**
  (`measurements/mutation/mutate_api013_hour_selection.log`). 1 test change, 0 implementation
  changes.

### What the hour selection is, and the two decisions inside it

| | |
|---|---|
| The capability | `GET /api/v1/operational-picture?run=<id>` serves that hour; `GET /api/v1/operational-picture/hours` lists the hours on offer |
| Why it was first | 400 stored runs, all examined, **240 holding a reportable claim, and the screen could reach exactly one** — whichever was newest |
| With no parameter | Unchanged. `api-002`'s guarantee, its parity test and the frontend contract are untouched |
| An unknown run | **404**, naming it, and never a fall back to the newest — the sharpest failure case, because falling back is indistinguishable from the feature working |
| A non-integer run | 422, following `api-007`'s rule that an unrecognised parameter never silently defaults |

**The chooser gets its own list, because the existing one carries the answer key.** Scenario
Control already fetches what a selector wants and carries each run's `scenario_type` — correctly,
that screen being the harness's own face. On the analyst's screen it is the answer key, and that is
the string `api-012` found in this screen's heading after a year. The guarantee has been
*structural* (a shape with no field for the answer cannot leak it); reusing the harness listing
would have downgraded it to a convention somebody has to know.

**The chooser says nothing about what was found, and this was nearly built the other way.** A
finding count per hour was the first design and was withdrawn — not because a conclusion is secret
(it is served in full for the hour selected) but because precision is 1.000 and per-run recall is
60 of 60 on every positive arm, so on this corpus ranking hours by findings ranks them by ground
truth. Any later exercise in which a person reads this screen would be un-blind with nothing in the
code recording it, and `eval-006` is still outstanding. What it does carry is **examined or not**,
which is a different kind of fact (`api-012`).

**Following and pinned are two states.** Pin an hour, let a batch land, and the screen keeps showing
the pinned hour while looking identical to a live one — the same class as `ops-005`'s healthy signal
over a broken endpoint. So the state is in words and there is always a way back. The poll follows
the selection rather than stopping: a historical hour's detection state can change (the re-score
restamped 380 runs in six minutes), and a poll still asking for the newest would revert the screen
under the analyst.

Smaller, and a repeat: the replayed window is read from what the run row records and is **null for a
run recording none** (a replay). Filling it from `started_at` would label a 2022 hour with the
wall-clock minute the generator ran, which is `anom-009`'s recorded mistake. The two clocks are four
years apart in the fixture so an implementation reaching for the nearest timestamp is caught by the
year.

### The basemap decision

**Default basemap offline; satellite a documented opt-in needing network.** Recorded in `map-001`
and `map-002` and argued in `thesis_notes.md`. Two consequences that were not obvious going in:

- **NFR-105 and AC-07 become claims about the default configuration.** The notes had already settled
  on self-hosting a vector basemap cut from OpenStreetMap, concluding that the hosted generator is
  then the only thing the system reaches for over a network. That sentence now needs "in its default
  configuration". The weaker form is still strong: the satellite source is off unless configured and
  nothing falls back to it.
- **The two basemaps are not peers.** Vector was chosen over raster precisely because raster arrives
  pre-rendered and competes with the overlays. Satellite *is* that. So the vector default is the
  working view and satellite is an orientation view, and `map-001` now says so — because when the
  map is built the two will look like a toggle, and a toggle implies interchangeable.

## Files in flight

None. The tree is clean.

## Changed

Commits, oldest first:

| Commit | Message |
|---|---|
| `ad07b7d` | `spec: amend map-001, map-002 — the basemap decision` |
| `9dba302` | `docs: progress note — the hours were examined, and the day it said it was fine` |
| `c134b2a` | `spec: add api-013, op-009` |
| `5cfa64b` | `test: add tests for api-013, op-009` |
| `c3fc833` | `feat(api-013, op-009): ask the screen for a particular hour - tests pass` |

**New files**

- `backend/tests/test_api_hour_selection.py` — 23 test functions, **48 collected** after
  parametrisation.
- `frontend/src/hooks/useSelectableHours.ts`.
- `frontend/src/test/hourSelection.test.tsx` — **18 cases**, including the structural check that
  no picture-side module names the harness fetcher, and its interlock.
- `backend/measurements/mutation/mutate_api013_hour_selection.py` + `.log`.

**Changed, backend**

- `app/dal/models.py` — `SelectableRun`, the repository-level row.
- `app/db/repository.py` — `selectable_hours` and `HOURS_LIMIT`.
- `app/api/v1/operational_picture.py` — the `run` parameter, the 404, and the index route.
- `app/api/v1/schemas/operational_picture.py` — `SelectableHour` and `SelectableHour.of`.
- `tests/test_api_operational_picture.py` — `SelectableHour` added to the parity map, so the
  existing parser check covers the new shape rather than a second parity suite.

**Changed, frontend**

- `src/lib/api.ts` — `fetchSelectableHours`, and `fetchOperationalPicture` takes a run.
- `src/hooks/useOperationalPicture.ts` — the poll follows the selection.
- `src/screens/operationalPicture.tsx` — the selector, the two states, `hourLabel`.
- `src/App.tsx` — the pinned-hour state in the picture route.
- `src/types/operationalPicture.ts` — the `SelectableHour` contract.
- `src/test/dataAccess.test.tsx` — two assertions amended, see Failed attempts.

**Docs**

- `docs/requirements.md` — FR-719, FR-811, AC-13.
- `docs/qa.md` — entry 146.
- `docs/thesis_notes.md` — two entries: the blind chooser, and the two-language mutation pass.
- `backend/measurements/README.md` — the mutation row, and the third hazard's third recurrence.
- `docs/progress_note.html` — published this session.

## Failed attempts

**A collection error is not a red run, and I had to be told that by the file I wrote.** The first
run of the new backend suite produced one `ImportError` and nothing else. That satisfies "the tests
fail" and establishes nothing — every test in the file fails that way regardless of what it
asserts, which this project already has written down. Against raising stubs: 19 of 34 failed, and
the 12 that passed were the **absence** assertions over an empty stub model. Proved load-bearing by
adding `scenarioType` and `findingCount` to the stub and watching five go red, then reverted.

**Three tests pass before the implementation and should.** The unchanged-default regression guard;
the one-shape check (an ignored parameter makes both shapes identical, so it cannot fail until the
parameter works); and the interlock firing the leak-scan at the harness listing. Named here so the
next pass does not read them as a gap.

**A test that compared a count with itself.** The polling test installed fake timers *after*
`render`, and an interval already scheduled on real timers is not adopted by a clock installed
later — so no second poll fired and `expect(2).toBeGreaterThan(2)` is what the failure actually
said. Fake timers now go before the render, as `dataAccess.test.tsx` already did.

**Two existing assertions stopped measuring what they were written to measure.** `dataAccess.test.tsx`
counted every `fetch` call, which was the same thing as counting the picture's own while one
endpoint existed. The index path also has the picture's path as a prefix, so one assertion passed
for the wrong reason and the other broke outright. Both now filter to picture calls. The tempting
alternative — stubbing the new fetch out of those tests — would have left them green over a route
whose new half was removed, which is the same mistake `anom-016` recorded with the launcher fakes.

**The mutation pass found a real gap, and it is the useful result.** Two mutants adding a field to
`SelectableRun` — the scenario type, and a finding count — survived. Every assertion was about the
shape that is *served*, and `SelectableHour.of` names its four fields explicitly, so neither reached
the wire: harmless, and a real gap. The item's claim is that the guarantee is **structural**, and it
was structural at one boundary and nowhere else — while the layer below is exactly where somebody
would add the field, in the query, to make the chooser more useful. Closed with two field-set
assertions over the repository row. The shape generalises `ops-005`'s survivor: **a guarantee
asserted where a value is serialised is not asserted where it is produced.**

**The OOM killer stopped the pass and left a mutant in the source — the third time.** Four mutants
into twenty-three, leaving `if False:` in place of the route's 404 branch, which is the item's own
sharpest failure case and invisible on screen. The guard file restored it and `git diff` against
committed code verified the claim rather than trusting it. The new finding is the cause: this pass
did **no** image builds and is not long by the earlier standard (~45 s a mutant), so twenty-three
`compose run` invocations is enough churn on its own and "no rebuilds, therefore safe" is not a
rule. The harness now takes `SIDE=frontend` / `SIDE=backend` so a pass can be taken in parts;
generalising that to the other harnesses is owed.

**`sleep` is blocked in this shell**, and chaining short sleeps to poll a background job is blocked
too. Long-running work goes to `run_in_background` or `Monitor` with an until-loop. Noted because I
lost two attempts to it.

## Next step

Items 2 to 5 of the screen sequence agreed on 2026-10-03, unchanged except that item 1 is now done
and the basemap decision no longer gates item 5.

1. ~~`api-002` gains a way to select an hour.~~ **Done** — `api-013`, `op-009`.
2. **The two header labels** (`op-001`, plus the system-status strip in the nav footer). The
   smallest item left: two correct values rendered as bare unlabelled words. `mixed` is
   `scenario.dataMode` and is right; `unknown` is `scenario.health` and is right because no health
   monitoring exists. **The scenario type must never be shown here** — that is `api-009`'s named
   failure case and it was live until `api-012`. Both items specced and unbuilt.
3. **The detection summary's vocabulary** (`op-003`, `ui-001`). Frontend only, no backend change:
   the payload carries finding types verbatim on purpose (`api-011`) and the screen never composed
   any copy. `op-006`'s timeline strip belongs here — carried in the payload and not rendered at
   all. Specced and unbuilt.
4. **Serve an evidence bundle**, so the summary can say *why* — which receivers deviated together,
   over what window, how far above normal, whether the aircraft side corroborated. All of it exists
   in the bundles and **no endpoint serves one**. **Not specced.** This is the thesis's own subject:
   the claim is explainability and the screen shows a conclusion with no route to what it rests on.
5. **The map** (`map-001`–`map-004`). Largest, and **no longer blocked** — the basemap decision is
   taken and recorded in the items. `map-001` now specifies two sources and `map-002` specifies what
   happens when neither is configured.

Then, unchanged:

6. **Re-run the figures of record.** `detection_metrics.py` imports the settings and builds its
   baseline through `measure_normality`. The values are unchanged, the equivalence is asserted at
   unit scale, and the re-score reproduced `eval-002`'s table exactly from stored rows — but
   `anom-015` validated its own refactor by reproducing all forty-three exported lines byte for
   byte, and that has not been done for this one.
7. **`hypotheses`**, the last producer-less field. 155 rows exist. Which arm an analyst sees,
   whether a row whose grounding check FAILED may be shown, and what `NOT_CHECKED` renders as.
8. **`eval-006`** still waits on a second rater, mid-October.

Open and unowned:

- **The hour chooser is blind by design, and that has a cost**: finding a particular staged hour
  depends on already knowing its number. Fine for the researcher — the numbers are in the
  measurement logs — and it means a demonstration to somebody else needs the hour chosen in advance.
  Recorded as a limitation in `qa.md` 146 rather than engineered around.
- **A pinned hour is not in the URL.** Considered and deferred: it would make an hour shareable and
  survive a reload, which is worth having for a demonstration, but `screenFromHash` resolves a bare
  screen id today so a parameterised hash is `nav-001`'s machinery and its own item, with its own
  failure case for an unrecognised run in a hash.
- **The index is fetched once per mount, not polled.** A batch completing while the screen is open
  does not appear in the list until the screen is remounted. Following the newest is unaffected —
  the endpoint with no parameter always serves the actual newest — so a stale list changes which
  hours are *offered* and never which hour is *shown*.
- **`docs/thesis_notes.md` is misfiled from about line 6800 onwards.** Everything after
  `## Evaluation` is appended there regardless of chapter. Not corrected mid-item; worth one pass
  before write-up. This session's two entries were placed in the right chapters.
- A `normal-baseline` batch is scored against a baseline that includes its own runs, because the
  baseline is a property of the store and not of the batch. Recorded rather than prevented.
- Nothing mechanical stops a **third** file declaring its own eleven detector settings. The guard
  catches the regrowth of the two copies that existed; the pin catches a change to the values. A new
  file is caught by neither.
