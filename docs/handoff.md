# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session ran 3–4 October 2026 and took items 1 to 3 of the agreed five-item screen sequence,
plus the basemap decision that had been blocking item 5.

1. **The basemap decision.** Default basemap offline; satellite a documented opt-in needing network.
2. **`api-013`, `op-009` — the screen can be asked for a particular hour.** The item that gated
   looking at the other four.
3. **`api-014`, `op-001`, `nav-002` — the two header labels.** Which turned out to be a requirement
   unmet since the shell was built, not a labelling fix.
4. **`op-003`, `op-006`, `ui-001` — the detection vocabulary**, the timeline strip, and one
   primitive for every level.
5. Housekeeping: **84.9 GB of Docker build cache cleared**, and the progress note brought current
   with two screenshots of the running system.

## Current state

Backlog **82 of 111**. Eight items landed this session; `map-001` and `map-002` were amended and are
still unbuilt.

- Backend: **1957 passed, 99.92% coverage, exit 0**, in containers (1895 at the start of the
  session).
- Frontend: **203 passed** (107 at the start), Biome lint clean, `tsc -b` clean. Still **no coverage
  tooling on that side**, which is why every frontend item here has a mutation pass instead.
- `make lint`, `make format` and mypy clean (79 source files).
- Mutation, three passes, **71 of 71 killed across both suites, no survivors, none equivalent**:
  `mutate_api013_hour_selection.log` (23), `mutate_op001_header_labels.log` (25),
  `mutate_op003_vocabulary.log` (23).
- The stack is up with the real store: 400 runs, all examined, `/api/v1/operational-picture` and
  `/api/v1/health` both 200.
- **A Vite dev server is running on `localhost:1234`** (IPv6 only — use `localhost`, not
  `127.0.0.1`). Started to take the screenshots; the container on `:8080` serves a built bundle and
  therefore the *old* UI until `make build-frontend`. Kill it with `pkill -f "em-fusion/frontend.*vite"`.

### What the screen does now

Two screenshots in `docs/screenshots/`, published in the progress note, taken against the real
store:

| | |
|---|---|
| `picture-staged-hour.jpg` | Run 420. Two of seven receivers deviating, anomaly **High**, integrity **Medium**, one interference claim worded as a sentence, one timeline entry at the replayed instant 12:13 |
| `picture-quiet-hour.jpg` | Run 400, pinned. All seven nominal, **Low/High**, both built rules **0**, the unbuilt one a dash, timeline saying in words that nothing happened |

Everything the three items added is visible in those two: the hour selector and its two states, the
labelled data mode, the standing badge and the system-status strip in the rail, conclusions as
sentences, and the timeline.

### The decisions worth carrying forward

**The hour chooser gets its own list, and says nothing about what was found.** Scenario Control's
runs listing carries each run's `scenario_type` — correctly, that screen being the harness's own
face — and on the analyst's screen that is the answer key. `api-009`'s guarantee has been
*structural* (a shape with no field for the answer cannot leak it); reusing the harness listing
would have downgraded it to a convention. And a finding count per hour was the first design and was
withdrawn: precision is 1.000 and per-run recall 60 of 60, so on this corpus ranking hours by
findings ranks them by ground truth, and any later exercise where a person reads this screen would
be un-blind with nothing recording it.

**The badge was one thing doing two jobs.** FR-703 wants a data-mode badge on *every* screen and no
screen had one — a requirement scoped across three screens implemented by an item scoped to one, and
invisible in the backlog for the same reason the producer-less fields were. *This system is not
live* depends on nothing, so it lives in the rail and reaches all three screens; *this hour is
synthetic RF plus replayed tracks* stays on the picture, labelled. The split is what makes the first
satisfiable, and it makes "unconditional" stronger than the item asked for: a badge with no input has
nothing present that can be absent.

**A 503 is an answer, not a failed request.** The status strip reads `/api/v1/health`, which
`ops-005` made meaningful. Connectivity is whether the request arrived; Service is what the backend
said about reaching its database. `fetchSystemHealth` is the one fetcher in that module that does
not throw on a non-2xx — read the other way, a misconfigured deployment reports as an outage, which
is the conflation that cost a day.

**Deleting `scenario.health` is the third route out of a producer-less field.** The earlier lesson
named two — produce it, or justify the emptiness — and both assume the field is wanted.
`api-012`'s `signalIntegrity` already does its job. `rfSensors[].health` stays: it has a producer and
is spelled identically, which is the whole risk in that removal.

**The copy is one module because two panels carry the same verbatim finding type.** The timeline's
`event` field holds `possible_interference_zone` exactly as the summary's counts do, so copy written
in either panel would need a second copy in the other, and one conclusion would get two sentences
with nothing to catch the drift. The reportable set is a contract union held against `anom-008`'s
register, so **a new detection rule cannot reach the screen without its wording being written**.

**A compile-time type is not a guard when the payload is cast.** `Level` is declared as exactly
three values, which refuses a number at the call site and cannot see the boundary that matters: the
payload is cast from JSON. Every guarantee this project enforces at a TypeScript type is enforced
only above that cast. The primitive renders no value, keeps the label so the row reads visibly
incomplete, logs the offending value, and never throws — the mutation pass measured the alternative
at 36 of 88 tests failing.

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
| `a779c00` | `measure: mutation pass over api-013 and op-009, and the gap it found` |
| `0007159` | `spec: amend op-001, nav-002; add api-014` |
| `abf43ea` | `test: add tests for api-014, op-001, nav-002` |
| `6454aa2` | `feat(api-014, op-001, nav-002): the two header labels - tests pass` |
| `1923043` | `measure: mutation pass over api-014, op-001, nav-002` |
| `1b08168` | `spec: amend op-003, op-006, ui-001 — the detection vocabulary` |
| `afda1cc` | `test: add tests for op-003, op-006, ui-001` |
| `fdef625` | `feat(op-003, op-006, ui-001): the detection vocabulary - tests pass` |
| `e45bae5` | `measure: mutation pass over op-003, op-006, ui-001` |

**New, backend**

- `tests/test_api_hour_selection.py` — 23 functions, 48 collected.
- `measurements/mutation/mutate_api013_hour_selection.py`, `mutate_op001_header_labels.py`,
  `mutate_op003_vocabulary.py`, each with its `.log`.

**New, frontend**

- `src/hooks/useSelectableHours.ts`, `src/hooks/useSystemHealth.ts`.
- `src/components/em/EmDataModeBadge.tsx`, `EmSystemStatus.tsx`, `EmLevel.tsx`.
- `src/lib/detectionVocabulary.ts`.
- `src/test/hourSelection.test.tsx`, `statusBar.test.tsx`, `systemStatus.test.tsx`,
  `levels.test.tsx`, `detectionVocabulary.test.tsx`.

**New, docs** — `docs/screenshots/picture-staged-hour.jpg`, `picture-quiet-hour.jpg`.

**Requirements** — FR-719, FR-811, AC-13.
**Q&A** — entries 146, 147, 148.

## Failed attempts

**A collection error is not a red run.** The first run of the hour-selection suite produced one
`ImportError`. That satisfies "the tests fail" and establishes nothing, which this project already
had written down. Against raising stubs: 19 of 34 failed, and the 12 that passed were absence
assertions over an empty stub, proved load-bearing by adding the forbidden fields and watching five
go red.

**Tests that cannot fail before the implementation, three times over, and they are not all the same
thing.** Some assert existing correct behaviour and must keep passing (the unchanged-default
regression guard, the interlock firing a leak-scan at the harness listing). Others pass only because
the feature is absent and establish nothing until the mutation pass (`does not become a fourth nav
entry`, `does not read the picture payload`). Worth telling apart when reading a red run.

**A test that compared a count with itself.** Fake timers installed *after* `render` do not adopt an
interval already scheduled on real timers, so no second poll fired and the failure read
`expect(2).toBeGreaterThan(2)`.

**Three existing assertions stopped measuring what they were written to measure**, all the same
shape: they counted *every* `fetch` as a proxy for one poll, which was equivalent only while one
endpoint existed. `dataAccess.test.tsx` twice (the hours path has the picture's as a prefix, so one
passed for the wrong reason), and `scenarioAccess.test.tsx` once — that one was *forbidding correct
behaviour*, since the status strip now polls from the rail on every screen. The tempting fix each
time was to stub the new fetch out, which would have left them green over a route whose new half was
removed.

**I changed two labels and the markup for no reason.** Routing levels through the primitive I
rewrote `Anomaly Level` → `Anomaly level` and swapped `<dt>/<dd>` for spans; four pre-existing tests
broke, correctly — they assert analyst-visible text and read the value as the `dd` beside its label.
Reverted both.

**I routed half the call sites.** `ui-001` names four; I did the summary panel's two. Caught by my
own test finding `74.2` in a hypothesis card. The behavioural form of that test is what made it
visible; a source scan would have passed.

**A test that was scanning its own documentation.** `test_the_field_is_absent_rather_than_optional`
searched the model's serialised JSON schema for the string `health` — and Pydantic carries a
docstring into the schema as `description`, so it failed on the prose explaining the removal. Now
reads the schema's `properties`, which is where a nullable field would appear. Same shape as the
checks here that were satisfied by a *comment* and had to be rewritten to parse rather than search.

**The mock had been unfaithful to its payload in two fields.** `event: "Anomaly Detected"` where the
real field carries a finding type verbatim, and `source: "Station Gamma"` where it carries a receiver
id. Written before anything produced either. It surfaced as *found multiple elements with the text:
Station Gamma* once the timeline rendered a source. The quiet version is worse: the prose `event`
renders through the copy module as **"Unrecognised finding type"**, so the pre-first-response
fallback would have shown a fault where the real payload shows a conclusion.

**The mutation pass found a real gap in the hour-selection tests.** Two mutants adding a field to
`SelectableRun` survived. Every assertion was about the shape that is *served*; neither reached the
wire, so both were harmless and the gap was real — the item's claim is that the guarantee is
structural, and it was structural at one boundary and nowhere else. **A guarantee asserted where a
value is serialised is not asserted where it is produced.**

**A mutation survivor that was the harness and not the code.** Restoring a field to the TypeScript
contract survived vitest — correctly, because the parser that guards it lives in the *backend*
suite. **Where a file lives and which suite guards it are different facts**, and dispatching on
location reported a green guard as a gap. `measurements/README.md`'s fifth hazard, second form; the
harness now dispatches on which suite guards a file.

**The eighth hazard, met a second time.** Flipping a producer from reportable to intermediate leaves
it with no measured background, which `Producer` refuses, so the module raised on import and the
suite reported errors rather than failures. The two instances break the same invariant class from
opposite directions — an ordering constraint and a mutual exclusion. The rule is now stated as a
procedure: import each mutated module and print what it yields *before* running the table.

**The OOM killer interrupted three runs**, once leaving a mutant in the source (`if False:` in place
of the 404 branch). The guard file restored it. Two findings: the pass did **no** image builds and
still died, so container churn alone is enough and "no rebuilds, therefore safe" is not a rule; and
a killed `compose run --rm` leaves an **orphaned container** holding memory, which makes the next
run likelier to die too. The harnesses now take `SIDE=frontend` / `SIDE=backend`.

**The collapsed badge was clipped, and no test could have caught it.** Looking at the running screen
showed `NOT LIVE` overflowing the 56px rail — the "E" past the border. The text was in the DOM and
the accessible name was correct, so every test passed. This is the project's recorded *third kind of
blind spot* in its purest form. Fixed by dropping the dot and tightening the padding when collapsed.

**`sleep` is blocked in this shell**, and chaining short sleeps to poll a background job is blocked
too. Use `run_in_background` or `Monitor` with an until-loop.

## Next step

Items 4 and 5 of the sequence agreed on 3 October, plus what was already behind them.

1. ~~A way to select an hour.~~ **Done** — `api-013`, `op-009`.
2. ~~The two header labels.~~ **Done** — `api-014`, `op-001`, `nav-002`.
3. ~~The detection summary's vocabulary and the timeline.~~ **Done** — `op-003`, `op-006`, `ui-001`.
4. **Serve an evidence bundle, so the screen can say *why*.** **Not specced**, and it is the
   project's own subject: the claim is explainability, and the screen states a conclusion with no
   route to what it rests on. The bundles exist — one per reported claim, every absence typed, every
   citation resolved against stored rows — and **no endpoint serves one**. What the panel needs is
   which receivers deviated together, over what window, how far above normal, and whether the
   aircraft side corroborated. Start by specifying the endpoint; the panel is the smaller half.
5. **The map** (`map-001`–`map-004`). Largest, specced, **no longer blocked**: `map-001` now
   specifies two basemap sources and `map-002` what happens when neither is configured.

Then, unchanged:

6. **Re-run the figures of record.** `detection_metrics.py` imports the settings and builds its
   baseline through `measure_normality`; the values are unchanged and the equivalence is asserted at
   unit scale, but `anom-015` validated its own refactor by reproducing all forty-three exported
   lines byte for byte and this one has not had that treatment.
7. **`hypotheses`**, the last producer-less field. 155 rows exist. Which arm an analyst sees,
   whether a row whose grounding check FAILED may be shown, and what `NOT_CHECKED` renders as.
8. **`eval-006`** still waits on a second rater, mid-October.

Open and unowned:

- **A figure quoted 7 times across the docs is stale.** `CLAUDE.md`, `docs/phase8_evidence_bundles.md`
  and `docs/qa.md` argue from "20.7M observations"; the store holds **15.5M** (13.5M track, 2.0M RF,
  the RF half exactly 400 × 5040 with nothing missing). Almost certainly a corpus-v1 figure that
  outlived its corpus. It sits inside the grounding-check tractability argument, so it wants
  correcting deliberately rather than by search-and-replace.
- **The hour chooser is blind by design**, so finding a particular staged hour means already knowing
  its number. Fine for the researcher; a demonstration to anybody else needs its hour picked in
  advance. The alternative was measured and rejected, not overlooked (`qa.md` 146).
- **A pinned hour is not in the URL.** Considered and deferred: `screenFromHash` resolves a bare
  screen id, so a parameterised hash is `nav-001`'s machinery and its own item.
- **The hour index is fetched once per mount, not polled.** A batch completing while the screen is
  open does not appear in the list until a remount. Following the newest is unaffected.
- **`docs/thesis_notes.md` is misfiled from about line 6900 onwards** — everything after
  `## Evaluation` is appended there regardless of chapter. This session's four entries were placed in
  the right chapters. Worth one pass before write-up.
- **The frontend container serves a stale bundle** until `make build-frontend`. Anyone looking at
  `:8080` sees the UI as it was before this session.
- A `normal-baseline` batch is scored against a baseline including its own runs, because the baseline
  is a property of the store and not of the batch. Recorded rather than prevented.
- Nothing mechanical stops a **third** file declaring its own eleven detector settings.
