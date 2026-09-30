# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session did one thing: **`api-011`, one batch at a time**. It is a defect fix rather than a
feature — starting several batches from the screen in quick succession left the backend serving
nothing at all — and it was chosen because `eval-006` is blocked until the second rater returns
mid-October and this was the only item in the backlog fixing something already broken in shipped
code.

It also closed a second, older defect found on the way: **the screen had no channel for a backend
refusal at all**, so every 422 the start endpoint had ever returned was invisible.

## Current state

Backlog **69 of 104**. Tree clean at `fe1eca3` plus the documentation commit.

- `backend/app/scenario/guard.py` — new, 39 statements, **100%**.
- `backend/app/api/v1/scenario.py`, `app/scenario/batch.py`,
  `app/api/v1/schemas/scenario.py` — changed; batch and schemas at **100%**.
- Backend suite: **1,465 passed / 288 skipped** locally; **1,751 passed at 99.92%** in containers.
  `make lint` and mypy clean.
- Frontend: **86 passed across 8 files, and it now exits 0** — see Failed attempts.
- Mutation: **17 of 17** (`mutate_api011_guard.log`), three files, no survivors.

### What the defect was, and what the fix claims

The backend was found hung on `QueuePool limit of size 5 overflow 10 reached, connection timed out`,
serving nothing, with its container reporting unhealthy. The cause is a **composition of two
correct decisions**, each separately tested: every start spawns an unbounded daemon thread
(`api-006`, so the request does not block for seventy seconds), and every thread borrows the
application's one Engine (`db-003`). Together they put batch work and request serving in competition
for a pool whose ceiling is SQLAlchemy's default fifteen, nothing in this project setting
`pool_size`.

The measurement that shaped the fix is the one saying what the defect is **not**: a single batch adds
one connection and `/health` answers 200 throughout. So this is not about batches being expensive,
and the remedy is to bound the count rather than to make a batch cheaper or the pool bigger.

What it claims: the observed cause is removed. What it does not claim: safety against arbitrary
load. It does not cancel a running batch, and it still does not report a batch that *failed* after
being accepted — the standing honesty gap.

### The five decisions worth carrying forward

| | |
|---|---|
| **Nothing is written to the database** | A batch cannot outlive its process, so a persisted *running* flag is a claim no crash can retract — `db-007`'s own argument for refusing a three-valued status column. In memory, a restart genuinely means nothing is in flight and the state says so by not existing. Held by a parsed-import check: the guard may not reach `app.db` or `sqlalchemy`. |
| **A lease, not a flag** | `launch_batch` returns in microseconds and the batch runs for seventy seconds, so releasing at the call site frees the guard before a run row is opened — **not a weaker guard but the absence of one**. The lease crosses the launcher seam and the thread's `finally` gives it back. |
| **Release means *if I am still the holder*** | Clearing unconditionally lets a thread finishing late free a bound a **later** batch holds, and then two batches run at once — the mechanism breaking the rule it enforces. |
| **Claimed in the handler body, never in a dependency** | A dependency resolves whether or not the body validates, so a guard claimed there is consumed by a 422 and the next valid start is refused on account of a batch that does not exist. |
| **Wall clock, deliberately** | `anom-009` records the opposite mistake. "How long has this batch been running" is a question about a real process, so this is the one place in the project where the wall clock is right — said out loud so it cannot later read as a repeat. |

### The refusal, and the channel that did not exist

A second start gets **409** with three fields and no fourth — type, base seed, start time — the key
set asserted exactly, so anything added later has to be argued for in that test rather than arriving
with the injected event in tow (`api-009`). **Facts, never prose**: the sentence an analyst reads is
composed on the screen, where the rest of that screen's copy already lives, and a body of fields is
assertable field by field where a sentence is assertable only by substring.

The screen could not say it. The scenario data source has computed a refusal since `api-010`;
`App.tsx` destructured the feed without it and the screen declared no prop for it. So **every 422 the
backend has ever returned produced no visible change at all** — an unknown scenario type, a batch
outside the permitted size, an incident starting after its run ends. Now: a prop, the wiring, and two
kinds of message, because a batch already running clears itself and a rejected configuration does
not.

## Files in flight

Tree is clean. Nothing half-finished.

## Changed

| Commit | What |
|---|---|
| `a310896` | `spec: amend api-011 — the lease, the refusal channel, and the clock` |
| `299c6bf` | `test: add tests for api-011` |
| `80ace99` | `feat(api-011): one batch at a time - tests pass` |
| `fe1eca3` | `test(api-011): mutation pass, 17 of 17` |

New files: `backend/app/scenario/guard.py`,
`backend/measurements/mutation/mutate_api011_guard.py` + `.log`.

Edited, backend: `app/api/v1/scenario.py` (the guard dependency, the 409, the release on a launcher
that raises), `app/api/v1/schemas/scenario.py` (`BatchInFlight`), `app/scenario/batch.py` (the lease
across the seam and the thread's `finally`), `tests/test_api_scenario.py` (+24 tests; `_post` now
binds a fresh guard per call and `RecordingLauncher` takes the lease), `tests/test_scn_control_contract.py`
(+2 parity tests over the 409 body).

Edited, frontend: `types/scenarioControl.ts` (`InFlightBatch`, `BatchRefusal`), `lib/api.ts`
(`BatchAlreadyRunningError`, and the 409 body read rather than discarded), `hooks/useScenarioControl.ts`
(`error: string` → `refusal: BatchRefusal`), `App.tsx` (the seam passes it),
`screens/scenarioControl.tsx` (the prop and two messages), `test/scenarioAccess.test.tsx` (+5),
`test/navigation.test.tsx` (the leaking fetch stub).

Edited, docs: `docs/spec.jsonl` (`api-011` amended with six findings, now passing),
`docs/qa.md` (§124-128 + 4 glossary rows), `docs/thesis_notes.md` (7 subsections, now 243),
`docs/implementation.md`, `backend/measurements/README.md`, `CLAUDE.md` (repo-map entry for the
guard).

No new dependencies. No new requirements. The progress note was **not** touched — this item changes
what the system does under load rather than the story the note tells, and nothing on it went stale.

## Failed attempts

- **The item's own scope line was wrong, and reading the code before writing tests is what caught
  it.** It said "one sentence of screen copy". There was nowhere to put a sentence: the feed computed
  a refusal, the seam dropped it, and the screen had no prop. Six findings went into the amendment
  before any test was written, and this one changed the scope rather than a detail.
- **The item said the launcher releases the guard in a `finally`.** It cannot: `launch_batch` starts a
  thread and returns. Released there, the guard is free before the batch has opened a run row, which
  is not a weaker bound but no bound — every later start would be accepted.
- **A frontend test passed before the implementation existed.** It asserted that no refusal is shown
  before anything has been refused, which was vacuously true while nothing rendered a refusal at all.
  The prove-red step is the only thing that said so. Replaced with a test requiring a refusal to
  appear and then clear.
- **The mutation pass found one survivor, and it was a real limit on what a test can observe.** A
  check-then-set `take` survived the barrier test, because two threads released together are usually
  scheduled so that one completes both halves before the other begins either. A test that catches a
  defect *occasionally* is worse than none, since it reads as coverage. Atomicity is now asserted
  against the parsed source — `take`'s body is one `with self._lock` and nothing beside it — with the
  behavioural test kept and annotated with what it leaves through.
- **Reasoning about mutants before running the harness found two gaps the suite already had.** Both
  posts in the refusal test carried one configuration, so a 409 naming the batch it had just refused
  was indistinguishable from one naming the running batch. And under the existing inline-thread
  stand-in a batch always finishes, so *released in the thread* and *released at the call site* looked
  identical; a stand-in that starts and never runs its target is what tells them apart.
- **The frontend suite had been passing and failing at the same time**, and the reassuring half was
  the one being read. All 86 tests passed while the runner exited non-zero on an unhandled exception:
  `navigation.test.tsx` stubbed the network to answer *every* path with the operational picture, so
  the scenario data source received a picture object as its run list and the screen called `.map` on
  it. Any CI gate over the frontend was broken regardless of the code. Fixed by answering per path, as
  the scenario suite already does — a defect in a test's fixture, which is the part of a suite nothing
  tests.
- **One frontend assertion was testing the wrong thing.** It expected the wire identifier
  `gnss-degradation` in the refusal; the screen renders the library's own name for the type, which is
  what the rest of that screen calls it. The screen was right and the test was changed, along with
  tightening the contract so the type travels as the closed set and the cast goes away.
- **`make format` reformatted unrelated files again.** Worked around by running `black` and `biome`
  on the files in hand. Standing item below.
- **Workflow deviation, recorded:** two backend tests and one structural test were added *after* first
  green, in response to the mutation pass. That is its purpose, but the order is worth noting.

## Next step

1. **`eval-006`** — the blind-score ingest and inter-rater agreement. Still the only thing between
   here and a complete evaluation chapter, and still blocked until the second rater returns
   mid-October.
2. **`eval-001`, possibly closeable by measurement rather than code.** Its failure case is a batch
   that cannot be reproduced from its recorded base seed — and until `scn-008` landed, base seeds were
   never stored, so that proof could not be taken. It is now in the run's recorded parameters, so the
   measurement is available. Cheap, and it keeps the evaluation chapter moving while the rater is
   away. Check first whether it is satisfiable before writing anything.
3. **The Hypotheses arc — the largest real gap, and all of it unblocked.** The system has produced 80
   hypothesis rows including a scored 20-bundle campaign and the application cannot display one of
   them; the human-in-the-loop half has no code at all, so AC-09 is undemonstrable and so are FR-711,
   FR-712 and FR-713. Ten items in one chain:
   `ui-001` → `api-004` → `hyp-001` → `hyp-002` → `hyp-003` → `hyp-004` → `ai-010` → `api-005` →
   `fbk-001` → `fbk-002`. Fold **`api-009`** in along the way rather than as its own arc: it is
   cross-cutting, assertable now, and `api-004` is exactly where a scenario type could leak into a
   response and quietly invalidate every metric already measured.
4. **A corpus with near-misses** is what would turn the detection table from a consistency result
   into an accuracy one. Out of scope for the dissertation, named as such in five places.

### Open and unowned

- **A malformed response from `/scenario/runs` would white-screen the application** rather than
  degrade — noticed while fixing the test above and deliberately not patched, because the honest
  posture (fail loudly, or render an explicit fault state) is a decision needing an item rather than
  a `try`. The other screen's data source was not audited the same way, so whether it drops or
  mishandles anything is not known.
- **Giving batch work its own Engine** is the complementary fix to `api-011` and stays available and
  unowned. Nothing sets `pool_size` or `max_overflow` either.
- **Reporting a batch that failed after acceptance.** `api-011` tells the analyst a batch is running;
  nothing tells them one died. Named out of scope on the item.
- **Serialising enough for the campaign record to round-trip** (`ai-012`) — **decided against, with a
  trigger.** Every benefit is conditional on a second campaign, which needs `ai-005`/`ai-006`, both
  unbuilt and both needing the unplanned local arm. **The trigger: do this first if a second campaign
  is ever run.** The one real exposure — the rebuild depends on the eighty stored rows — is closed by
  the committed per-call split, written only after its reconciliation passes.
- **`cost_is_complete` is vacuously true on an arm that made no calls** — the same defect `eval-005`
  fixed for its rates, surviving in the one field that is a boolean rather than a rate. Recorded, not
  changed.
- Mutation harnesses for the four other evaluation modules — `pack.py`, `sampling.py`,
  `statistics.py`, `workbook.py` — 104 tests with nothing establishing they are load-bearing. The
  three harnesses written recently found ten real gaps between them, which is the argument.
- Six measurement harnesses lack the guard-file-and-sentinel pattern; only the four most recent check
  that a mutant parses and is not identical to the original.
- The 0.39 rate-excess singleton, seen once at n=40 and surviving to n=60 with no second example.
- 12 files not Black-formatted; `make format` touches them on every run.
- Nothing applies migrations to the application database in the ordinary path.
- `ai-011`'s harness has not been re-run since the corpus was regenerated.
- The credential loader is not generalised.
- `ai-008`'s superseded case has no corpus demonstration.
- `docs/phase9_hypothesis_layer.md` §8 still says N=1, which the twenty-bundle agreement figures
  settle.
- Rebuilding evidence bundles corpus-wide would renumber the scored population (bundle ids 247-308)
  and stop `draw_scored_sample.py` reproducing its own draw.
- The three progress-note charts still want a real visual pass; the browser extension was unavailable
  when they were drawn, and geometry was verified arithmetically instead.

### Two limitations from earlier sessions that must not be dropped

**The detection table measures wiring, not accuracy.** Every rate is 1.000 or 0.000. The radio side
is synthetic with the incident well above threshold by construction, the corpus holds no near-misses,
and one of three reportable types has no rule. The only figure carrying information from outside the
generator is the per-aircraft recall, 0.587 on two arms of three.

**The retry and fallback paths never fired.** Nothing was refused and nothing fell back on the scored
campaign, so a fallback rate of zero reports that the path was *not exercised* — not that it works.
