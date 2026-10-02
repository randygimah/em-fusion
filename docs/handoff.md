# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

One item this session, and it is the second half of the question that reframed the roadmap last
session — *does detector output on injected anomalies show in the app at all?*

**`api-012`, the operational picture carries detection.** The main screen's detection panel,
receiver strip and timeline have been on screen since the first week and fed nothing. The endpoint
served a hard-coded empty list for the sensors, an empty list for the timeline and two nulls for the
summary, under a justification — *no detector, RF source or generator exists* — that was true when
written and false once eight rules, the synthetic source, the generator, 103 bundles and 155
hypothesis rows existed. Nothing noticed, because three items *consume* those fields and no item
produced them.

Building it reopened **`anom-015`**, whose amendment is half the work: the detection pass persisted
its evidence and not its conclusions, and nothing recorded that it had run.

## Current state

Backlog **72 of 106** (`anom-015` was reopened by its amendment and re-closed; `api-012` is new).
Tree clean at the write-up commit, which is the last on `main`.

- Backend: **1,830 passed, 99% total coverage, exit 0**, in containers.
- Every module this item touched is at **100%**: `app/api/v1/schemas/operational_picture.py` (155
  statements), `app/detection/chain.py` (109), `app/db/repository.py` (78), `app/detection/findings.py`
  (36), `app/api/v1/operational_picture.py` (15).
- Frontend: **89 passed across 8 files, exit 0** (86 before).
- `make lint`, `make format` and mypy clean (78 source files).
- Mutation: **33 of 33 killed, no survivors** over four files
  (`measurements/mutation/mutate_api012_detection_payload.log`). First pass: 26 of 28 valid, five
  invalid anchors (black had reflowed three of the lines after the table was drafted — recorded as
  the seventh hazard in `measurements/README.md`), and two real survivors, both test gaps rather
  than figures. 2 tests strengthened, 0 implementation changes.

### What the payload now carries

| Section | Before | Now |
|---|---|---|
| `detectionSummary` | two nulls, always | `null` when no pass has run; otherwise two levels and an **account** of every registered rule |
| `rfSensors` | `[]` | all seven of `scn-005`'s receivers, with `health` — `unknown` without a pass, else `nominal`/`deviating`/`fault` |
| `timelineEvents` | `[]` | the reportable claims, oldest first, finding type verbatim |
| `scenario.name` | **the run's scenario type** (`gnss-degradation`) | `Run <id>` |
| `hypotheses` | `[]` | `[]` — the one section still empty, and now named as such |

### The three things worth knowing

**Zero was unrecordable.** The item's sharpest constraint is that an unexamined run must not produce
the same payload as a quiet one, and no mechanism existed: findings are replaced per run per rule
*including at zero*, so examined-and-clean, re-examined-and-clean, never-examined and
pointed-at-the-wrong-observations all leave an identical empty table. Three are failures. So
`0009_detection_pass_stamp.py` puts `detection_pass_at` and `detection_policy` on `scenario_runs`,
nullable, absence meaning *not known to have been scored* — parallel to `db-007`'s completion stamp.
The pass stamps **last**, after every write, so a pass that dies part-way leaves a run that is not
known to have been scored rather than one claiming an examination it did not finish.

**The pass persisted its evidence and not its conclusions.** `anom-015` wrote the radio deviations
and the track gaps, both because *later* rules query those rows. The two rules at the end of the
ladder returned their claims on the `Assessment` and wrote nowhere — invisible inside one process,
and from a web request the conclusions do not exist. The premise that hid it had expired between the
amendment and the code: the item recorded the bundle as the reportable claim's persisted form, true
of 103 rows a measurement script had stored and never true of this pass, which withdrew bundle
storage on `eval-004`'s argument. Reported claims are now `db-008` findings, suppressed ones never.

**The heading announced the answer key.** `scenario.name` was the run's scenario type, so the screen's
`h1` read `gnss-degradation` — `api-009`'s named failure case, live, in every screenshot of that
screen so far. It survived because `ScenarioRunSummary` was built with no ground-truth field and the
check stopped there: *the type is not the event, it is the label for it*, and it discloses the
mechanism, the band, and that anything was injected. Invisible to a repository-wide search, because
the same string is legitimate on Scenario Control and disqualifying here. Now asserted over the
serialised payload across all five arms.

## Files in flight

None. The tree is clean.

## Changed

Commits, oldest first:

| Commit | Message |
|---|---|
| `f834b27` | `spec: amend anom-015, api-012, api-002` |
| `addbe06` | `spec: amend api-012 — one absence, one meaning` |
| `61a8532` | `test: add tests for api-012, anom-015 (amended)` |
| `48cdee9` | `style: make format over twelve files committed unformatted` (unrelated to this item; AST-identical except one docstring black spaced) |
| `9a22279` | `feat(api-012, anom-015): the picture carries detection - tests pass` |
| *last on `main`* | `docs: api-012 write-up` |

**New files**

- `backend/alembic/versions/0009_detection_pass_stamp.py` — two nullable columns on `scenario_runs`.
- `backend/measurements/mutation/mutate_api012_detection_payload.py` + `.log`.

**Changed, backend**

- `app/dal/models.py` — `DetectionPass`. A separate object, not two fields on `ScenarioRunSummary`:
  carried there it would travel to `/scenario/runs`, where `api-006`'s contract does not ask for it,
  and a nullable pair makes a stamp without its policy representable.
- `app/db/repository.py` — `record_detection_pass`, `detection_pass_for_run`.
- `app/detection/findings.py` — `from_sensor_fault`, `from_interference_zone`. No refs: both rules
  reason about another rule's output and measure nothing, which is `evb-001`'s `DERIVED`.
- `app/detection/chain.py` — `reported_findings` (pure, identity-matched), the two writes, the stamp.
- `app/api/v1/schemas/operational_picture.py` — `DetectionCount`, the reshaped `DetectionSummary`,
  `PERSISTED_PRODUCERS`, `RECEIVER_STATES`, `_level`, `_band`, `_receiver_health`, `_account`,
  `_detection_summary`, `_timeline`.
- `app/api/v1/operational_picture.py` — four reads and the layout.
- `tests/test_api_route_purity.py` — allowlist widened by one module, with a guard on the allowlist.

**Changed, frontend**

- `types/operationalPicture.ts` — `ProducerKind`, `CountUnavailable`, `DetectionCount`, nullable
  `detectionSummary`, non-nullable inner levels.
- `mocks/operationalPictureMock.ts`, `screens/operationalPicture.tsx`,
  `test/operationalPicture.test.tsx`, `test/dataAccess.test.tsx`.

## Failed attempts

**Three concurrent test suites, diagnosed as a migration defect.** A full-suite run reported 33
failures and 158 errors with `relation "scenario_runs" does not exist` and PostgreSQL deadlocks
between two processes. The first suspicion was the new migration and it was wrong: the migration
applies cleanly from empty, the test database was at head with every table present, and each
affected file passed alone. The cause was mine — three suites running at once against the same test
database, started because the first two had produced no visible output and were assumed finished.
Every database test drops and recreates the schema, so they dropped it under one another. The suite
is serial and shares one database by design, which makes it safe to run and unsafe to run twice, and
nothing in the tooling says so.

**A test that passed before its implementation, again.** The frontend test asserting that a
*scored-clean* run does not say "no detection pass" passed during the red run — vacuously, since the
screen never said it. Folded into one test that renders both payloads and requires the sentence in
one and not the other, which cannot pass that way. Same shape as `api-011`'s, and the second time
prove-red has caught it.

**A live test that was vacuous for a month.** `test_the_payload_carries_no_decimal_score` fetched
`detectionSummary` from the endpoint and asserted every value was a level or null — on a payload
whose summary was *always* two nulls, so it held whatever the levels would have been. It failed on
the full-suite run (`.values()` on `None`) and was rewritten against a **scored** run, which is the
only payload that can carry a decimal.

**I edited a source file while the container suite was running**, which bind-mounts the source. The
run's result was valid (the module was already imported) but the figure was for pre-edit code, so
the whole suite was re-run. Worth not repeating.

**A guard whose allowlist named a module where it meant a role.** The route purity check admits
`app.db.repository` and `app.db.session` only, and serving stored findings needed
`app.db.findings` — a repository function in a package that grew three more such modules after the
check was written. Widened by the one module needed, not by a prefix, with a new guard on the
allowlist (every entry exists, is a storage module, and is not a storage engine) and the check's
three real rules untouched.

**The spec was amended twice, and the second was a correction to the first.** The first amendment
kept the two level fields nullable so a pass that could judge no cell could not report clean.
Designing the assembly showed the data cannot carry that: `anom-001`'s unjudged cells are a list of
cells, nothing persists them, and from the findings table *judged everything, found nothing* and
*judged nothing* are the same empty result. A nullability whose meaning no stored value can
establish reads as a distinction being made, so the summary's own absence became the only absence,
with the gap recorded as a limitation.

## Next step

1. **Fire the pass when a batch completes.** Not yet specced. At 1.22 s a run plus 11.2 s of
   baseline it belongs at the end of a generation batch and not inside a five-second poll
   (`api-003`), so until it exists every run honestly reports as unexamined and nothing on screen
   changes without scoring a run by hand. This is the shortest remaining path to the user seeing
   detection output. Its own constraints are already visible: a pass that fails must not fail the
   batch (`scn-003`'s record-and-skip), and a store with no quiet runs must refuse rather than
   baseline against staged data — which a fresh database always is.
2. **Re-score the corpus**, once 1 exists or by hand. The 300 stored runs have findings and **no
   stamp**, so every one of them reads as unexamined — which is correct and is also why the screen
   will show nothing until the pass is re-run. ~6 minutes at 1.22 s a run.
3. **`op-003` and `op-006`**, the two panels this item unblocked. Both now have a producer for the
   first time; the summary panel is deliberately minimal and the timeline strip is not rendered at
   all.
4. **`hypotheses`**, the last producer-less field. 155 rows exist. Its own questions: which arm an
   analyst sees, whether a row whose grounding check FAILED may be shown, and what `db-002`'s
   three-valued `NOT_CHECKED` renders as.
5. **`eval-006`** still waits on a second rater, mid-October.

Open and unowned:

- The progress note has not been updated for `anom-015` or `api-012`, and both change the story it
  tells — the pipeline spine's detection stage and the "what it deliberately does not do yet"
  section. Offer before the next item.
- This boundary cannot distinguish a receiver *measured and nominal* from one whose cells had **no
  baseline**, because `anom-001`'s unjudged cells are not persisted. Recorded as a limitation on
  `_receiver_health`; the fix belongs to whatever stores them.
- With bundles unstored, a **suppression is persisted nowhere**, so the ladder's own workings are
  reconstructible only by re-running the pass.
