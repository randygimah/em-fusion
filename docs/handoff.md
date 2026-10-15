# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session (9–15 October 2026) did eight things:

1. **Finished playback.** `api-018` serves each receiver's out-of-nominal intervals through an hour;
   `map-007` draws receivers in their state at the playback cursor.
2. **Supported the blind scoring.** `eval-010` built the pass-two answer sheet the rubric promised and
   nothing produced. The user (first rater) then finished both passes. On their feedback (three hours,
   not ninety minutes; near-duplicate packs in blocks), `eval-011` cut the second rater's set to ten
   packs in an alternating order.
3. **Started the Hypotheses screen**, unparked once the user's scoring was done:
   - `db-012`: each stored hypothesis's position in its campaign;
   - `api-004`: the hypothesis read endpoints;
   - `api-019`: the picture serves the hour's explanations;
   - `op-002`: the rail's cards;
   - `nav-004`: each explanation's own address.
4. **Kept the progress note current** (published versions 10 and 11).
5. **Built the Hypotheses screen itself** (11–12 October): `hyp-001`–`hyp-003` amended to what is
   stored, then built, which also finished `ai-010`.
6. **Built the verdict endpoint** (13 October): `api-005` amended to pin the verdict → status
   mapping, then built; the main database migrated to `0011`.
7. **Built the verdict card** (13–15 October): `fbk-001`, `fbk-002` and `hyp-004` amended to what
   `api-005` built, then built as one piece (one card in the design), on the user's agreement.
8. **Built the third source (`adp-003`)**, a receiver health feed, and took RQ1's extensibility
   measurement. Scoping it first found and fixed a phantom aircraft (`api-020`) before the clock
   started.

Everything went spec → failing tests → code → user review (→ mutation pass for frontend items) →
`passes: true`, committed on `main`.

## Current state

**Backlog 120 of 129.** `main` is in sync with `origin/main`; tree clean once this handoff is
committed.

**Suites:**
- Backend, full container suite: **2,368 passed, 99.90%** (6,107 statements, 6 missed; 12 min 14 s),
  run with `adp-003` in place on 15 October; the three new `adp-003` files are at 100%.
- Frontend: **616 passed** (25 new in `hypothesisVerdict.test.tsx`); Biome lint and `tsc -b` clean.

**The main database is migrated to `0011`** (`/api/v1/health` reports `at-head`). The `0010` ordinal
copy ran earlier: 80 positions written from the committed campaign record; a second run wrote 0.

### The verdict endpoint (`api-005`)

- `POST /api/v1/hypotheses/{id}/feedback`, body `{verdict, note}`:
  - confirm → Confirmed; reject → Rejected; false-positive → Rejected (the verdict kept on the row);
    needs-more-evidence → Under review. Inconclusive stays in the stored set, unused.
  - The latest verdict sets the status, from any status; verdicts are appended, never replaced.
  - Only the reviewable row takes one (409 otherwise); unknown id 404; bad verdict or a note over
    2,000 characters 422; a blank note is stored as null.
  - The verdict row and the status change are one transaction. The reply is the detail as stored.
- Migration `0011` adds a CHECK holding the four verdicts in the store.
- **Checked live against the main database, refusals only:** a bad verdict and a 2,001-character note
  on 104 (422), id 999999 (404), 105 (a hosted repeat) and 107 (template) (409). Afterwards
  `analyst_feedback` held 0 rows and every hypothesis was still New.

### The verdict card (`fbk-001`, `fbk-002`, `hyp-004`)

- **Where:** the Hypotheses screen's right column, under the map. Note box (optional, counted against
  2,000, never truncated: over the limit the buttons are disabled with a sentence), four buttons
  (Confirm, Reject, Needs more evidence, False positive), the disclaimer *Decision support only —
  analyst judgement is final.* under them, on every explanation including those that take no verdict.
- **Behaviour:** one click, no confirmation step. Buttons disabled while sending. After a verdict the
  header, the list and the history show **the store's reply** (held per explanation in the screen);
  a refusal, a network failure or a reply naming another explanation changes nothing but a sentence
  and keeps the note. A non-reviewable row shows a sentence and no controls. History in words.
- **Mutation:** `mutate_fbk001_002_hyp004.log`, **30 of 30** on the second run, sentinel killed (91
  tests in four suites). First run 29 of 31; see Failed attempts.
- **Checked in the browser** (13 October, no click): the card on `#/hypotheses/104` at 1456 px and
  the no-verdict sentence on 105; no console errors.
- **The user tested it in the app (15 October) and recorded the first real verdicts in the main
  store:** 148 Confirm (with a note) → Confirmed; 96 Needs more evidence (with a note) → Under review.
  The store now holds 2 feedback rows; statuses New 153, Confirmed 1, Under review 1.

### The Hypotheses screen, as far as it goes

- **What an analyst reviews.** One explanation per conclusion, the *reviewable* row: asked of the
  hosted arm at eval-004's `SCORED_ORDINAL`, so a verdict and a blind score refer to the same text.
  - The store holds 155 hypotheses over 20 bundles: 5–6 hosted rows and 2 template rows per bundle,
    plus trial rows written before the campaign.
  - Before `db-012` the store could not say which row was scored. The earliest row by id was the
    scored one on **0 of 20** bundles.
- **`GET /api/v1/hypotheses`** lists the 20 reviewable rows, exactly the campaign record's scored
  hosted rows (checked). Also: `unreviewableBundles` 0, none fell back, model `gpt-4.1-2025-04-14`,
  confidence High 11 / Medium 9. 209 ms, 8 KB.
- **`GET /api/v1/hypotheses/{id}`** serves any stored row, saying whether it is reviewable:
  - every citation's grounding re-run on read (all 70 grounded), with the stored verdict served beside it;
  - the bundle's context;
  - the verdict history (`analyst_feedback` is still empty).
- **The picture** serves `hypotheses` (the list endpoint's own summaries) and
  `unexplainedConclusions` (null when unexamined). Over the 460 hours the screen offers:
  - 20 hours serve one explanation;
  - 261 hold one to three conclusions with none;
  - 199 hold no conclusion.

  The added reads cost 1.7 ms median (max 27.9 ms) on a 110–127 ms picture.
- **The rail** (heading a fixed "Hypotheses"):
  - **Cards:** one per explanation, any status. Each is a link to `#/hypotheses/<id>` with the title,
    confidence, a status badge (New tinted primary, others neutral), and provenance in words
    ("Written by the AI model, gpt-4.1-2025-04-14"). A fallback names both arms and is styled as a
    warning.
  - **The sentence** under the cards: "N conclusion(s) this hour have no explanation yet" / "No
    conclusions this hour" / "This hour has not been examined".
  - **The mock** carries no explanation, so nothing invented flashes before the first poll.
- **The address.** `#/hypotheses/<id>` opens the Hypotheses screen on that explanation, marked
  current in the rail. A malformed id is no id, never a guessed one.
- **The screen** (`hyp-001`–`hyp-003`, `ai-010`):
  - **List:** the 20 reviewable explanations, the open one marked; an empty list counts
    `unreviewableBundles`.
  - **Header:** title, status pill (`EmStatusPill`, now shared with the rail), confidence through
    `EmLevel`, window, run, subject, the receivers the evidence names, and the centre.
  - **Provenance** in the rail's words.
  - **Summary, recommended action** and **verdict history** (read-only; empty everywhere today).
  - **Evidence:** one row per citation (rule chip, finding in words, statement, the re-check's word);
    a failing citation is shown and marked. The stored check is stated once above, unreconciled.
  - **Doubts:** two sections, *None recorded* when empty, no category tags.
  - **Map of the affected area** (`qa.md` §164): zoomed to the disc at the recorded radius and the
    named receivers, drawn flat with no heat-map gradient, coordinates underneath. A fault gets no
    disc and a sentence saying why.
  - **Failure states:** not found (404), a failed load, an answer for another id refused, a slow
    answer for a stale address dropped, the map's hour failing alone.
- **Zone matching, measured** against the store on 11 October: all 10 interference explanations
  matched exactly one zone (receivers, window and centre identical, radius 60 km); all 10 fault
  explanations had none.
- **Checked in the browser:**
  - `#/hypotheses/104` (interference: the disc round RF-04 and RF-05) and `#/hypotheses/148` (fault:
    RF-05–07, no disc, the sentence), no console errors, at 1456 px;
  - run 102's card → `#/hypotheses/76`;
  - run 480 reads "1 conclusion this hour has no explanation yet";
  - run 123 shows the NEW badge;
  - the Detection Summary heading now matches Hypotheses (colour, size, font).
- **The twenty runs with an explanation** are listed in `docs/evaluation_harness.md` ("Where the
  scored explanations are on screen"): 102–118 interference, 123–137 sensor fault, 161–175
  mixed evidence.
- **Mutation:**
  - `mutate_op002_nav004.log`: **22 of 22** on the first run (styling not mutated).
  - `mutate_hyp001_003.log`: **42 of 42** on the second run, sentinel killed (195 tests in the
    eight suites run). The first run killed 40 of 42; see Failed attempts.

### The phantom aircraft (`api-020`) and the third source (`adp-003`)

- **Found 15 October while scoping `adp-003`:** `latest_positions` grouped the final window by
  `payload->>'aircraft_id'` with no type filter, so every synthetic run's radio readings fell into
  one null group and the newest was served as a nameless aircraft (runs 102, 123, 161, 300, 480: one
  each; on 480 sitting on RF-05, nominal). Fixed: tracks only, and the window measured from the
  newest track (equal to the newest row on all 460 runs, so no change today).
- **Live after the fix:** 480 420→419, 102 428→427, 123 419→418, 161 419→418; none nameless.
- **`adp-003` is done** (`75ed33c`). `app/scenario/receiver_health.py` (`emit_health(layout, seed,
  start, duration_seconds)`, one report per receiver per 60 s) and `app/adapters/receiver_health.py`
  (`emit_run`, keyword-only after the layout), registered in `app/dal/models.py` only
  (`SYNTHETIC_HEALTH`, `RECEIVER_HEALTH`, `ReceiverHealthPayload`). Wired into nothing: no stored run
  has health reports and the main store is untouched.
- **The measurement** (`measurements/extensibility/adp003_extensibility.{py,log}`, `269c894..75ed33c`):
  2 new app files +112; `models.py` +17 −1; tests +519; **0 protected paths touched**. Clock
  19:11:59–21:13:58 UTC: 2 h 2 min elapsed, 1 h 44 min 45 s waiting for the user (two waits, declared
  in the script from the transcript), **17 min 14 s active**, of which the suite ran 12 min 14 s.
  Written up in `thesis_notes.md` with its threats.

### The blind scoring

- **First rater (the user):** both passes done in `scoring_pack/score_sheet1.xlsx` (not opened by
  this session).
  - About **three hours** for 40 items, against the rubric's ninety minutes.
  - They saw the arm key between passes, so their pass two is reported as unblinded.
- **Answer sheet** (`eval-010`): `scoring_pack/answer_sheet.md`, one fixed sentence per scenario type
  from `scn-002`. All 20 packs are about their run's staged incident.
  - On the five mixed-evidence packs (00288, 00289, 00295, 00299, 00302) no staged aircraft reaches
    the evidence, because the sensor-fault verdict stops the aircraft side being consulted.
  - Their cause correctness is reported separately.
- **Second rater's set** (`eval-011`): `scoring_pack_rater2/` holds `hypotheses.md`,
  `score_sheet2.xlsx` and `answer_sheet.md`, and no arm key.
  - 10 packs / 20 items / 140 values, drawn with seed 20261010 and quota 5 / 3 / 2.
  - Order 00280, 00250, 00289, 00254, 00279, 00262, 00302, 00248, 00273, 00264 (kinds alternate).
  - Each pack is byte-identical to the first rater's apart from its heading, so the sheets join on
    item id.
  - The user's other 20 items stay as single-rated; κ is over the 20 double-scored items.

### Playback (finished)

- `api-018`: 3,220 of 3,220 receiver-hours have a worst interval equal to the picture's whole-hour
  state; 338 B median, 7 ms median.
- `map-007`: on run 480, RF-01 is fault 12:38:51–12:44:01 and nominal either side. Mutation 22 of 22
  (second run).

### The progress note

Published version 11 (private link in the session record; `docs/progress_note.html` is the master). It
covers the first marker's pass and the second marker's ten packages. **It says nothing yet about the
Hypotheses screen** (`db-012` onward), which now shows enough to tell.

## Files in flight

None. The tree is clean once this handoff is committed (`docs/EM_Fusion_literature_matrix.xlsx` is
the user's untracked file; leave it).

## Changed

| Commit | Message |
|---|---|
| `904eb55` | `test: add tests for api-018` |
| `725d163` | `docs: qa 160, the pass-2 answer sheet was never built` |
| `484d073` | `feat: completed score sheet` (the user's commit) |
| `2c7af38` | `spec: add eval-010 -- the pass-2 answer sheet; correct qa 160` |
| `59f77e8` | `test: add tests for eval-010` |
| `f2af32b` | `chore: remove Office lock files from the scoring pack; ignore them` |
| `25a527f` | `feat(eval-010): the pass-two answer sheet - tests pass` |
| `ceb869f` | `fix(eval-010): mount spec.jsonl into the test container for the pre-campaign wording check` |
| `2bdc0b6` | `feat(api-018): receiver states over the hour - tests pass` |
| `0231b06` | `test: add tests for map-007` |
| `456adc3` | `feat(map-007): receivers in their state at the playback cursor - tests pass` |
| `98befe2` | `docs: progress note covers receivers through the hour and the answer sheet` (version 10) |
| `2be2c64` | `docs: first rater's scoring time and the proposal to cut the second rater's corpus` |
| `dc73479` | `spec: add eval-011` (amends `eval-006`: κ over the double-scored items only) |
| `f45cce4` | `test: add tests for eval-011` |
| `3ada952` | `feat(eval-011): the second rater's ten packs, drawn and alternating - tests pass` |
| `e17a5b2` | `docs: progress note covers the first marker's pass and the second marker's ten packages` (version 11) |
| `8be5857` | `spec: add db-012, amend api-004` |
| `404a5dc` | `test: add tests for db-012, api-004` |
| `2e57ad9` | `feat(db-012, api-004): campaign position and the hypothesis read endpoints - tests pass` |
| `0818adf` | `spec: add api-019` |
| `0a106cd` | `test: add tests for api-019` |
| `3818195` | `feat(api-019): the picture serves the hour's explanations - tests pass` |
| `5d2c351` | `spec: amend op-002, add nav-004` |
| `5ed979b` | `test: add tests for op-002, nav-004` |
| `0b9f057` | `spec: amend api-004, op-002 -- name the model, heading Hypotheses` |
| `57c4a0c` | `test: add tests for api-004, op-002 amendments` (also carries the op-002/nav-004 code; see Failed attempts) |
| `a67daf5` | `feat(op-002, nav-004): the rail's cards and each explanation's address - tests pass` |
| `794b46b` | `docs: handoff for the hypotheses rail and address` |
| `409bf2b` | `spec: amend hyp-001, hyp-002, hyp-003 -- the screen against what is stored` |
| `e9baeda` | `test: add tests for hyp-001, hyp-002, hyp-003` |
| `ccc5b0b` | `feat(hyp-001, hyp-002, hyp-003, ai-010): the Hypotheses screen - tests pass` |
| `c7af518` | `docs: progress note covers the Hypotheses screen (version 12)` |
| `9d00d7a` | `docs: qa 165, the next strands of work` |
| `c4a7b2a` | `spec: amend api-005 -- the verdict-to-status mapping` |
| `da88dfd` | `test: add tests for api-005` |
| `9ebd6b1` | `feat(api-005): the analyst's verdict and the status it sets - tests pass` |
| `b6f459d` | `spec: amend fbk-001, fbk-002, hyp-004 -- the verdict card` |
| `27e4d21` | `test: add tests for fbk-001, fbk-002, hyp-004` |
| `1c3684a` | `feat(fbk-001, fbk-002, hyp-004): the verdict card - tests pass` |
| `09066cf` | `docs: progress note covers the verdict card and the first two verdicts (version 13)` |
| `00183f0` | `docs: qa 166, the next implementation while the second scorer works` |
| `3039ab0` | `spec: add api-020 -- the picture's aircraft are aircraft` |
| `e05cd56` | `test: add tests for api-020` |
| `269c894` | `fix(api-020): the picture's aircraft are aircraft - tests pass` |
| `66b1c00` | `spec: amend adp-003 -- a receiver health feed, and what must stay unchanged` |
| `f09cc78` | `spec: adp-003 hours reported without the waits for the user` |
| `6de44da` | `test: add tests for adp-003` |
| `75ed33c` | `feat(adp-003): a receiver health feed, by registration only - tests pass` |
| *(this commit)* | `docs: adp-003 extensibility measurement and notes` |

**New files:**
- **Backend:**
  - `alembic/versions/0010_campaign_ordinal.py`;
  - `app/api/v1/hypotheses.py` and `app/api/v1/schemas/hypotheses.py`;
  - `app/api/v1/schemas/receiver_states.py`;
  - `app/evaluation/answers.py`.
- **Backend tests:** `test_db_campaign_ordinal.py`, `test_api_hypotheses.py`,
  `test_api_picture_hypotheses.py`, `test_api_receiver_states.py`, `test_eval_answer_sheet.py`,
  `test_eval_rater_subset.py`.
- **Measurements:**
  - `corpus/backfill_campaign_ordinal.{py,log}`;
  - `corpus/build_answer_sheet.{py,log}` and `corpus/build_rater2_pack.{py,log}`;
  - `corpus/receiver_states_agreement.{py,log}`;
  - `corpus/scoring_pack_rater2/`;
  - `mutation/mutate_map007_receivers.{py,log}` and `mutation/mutate_op002_nav004.{py,log}`.
- **Frontend:**
  - `types/hypotheses.ts`;
  - `lib/hypothesisVocabulary.ts` and `lib/receiverPlayback.ts`;
  - `hooks/useReceiverStates.ts`.
- **Frontend tests:** `hypothesisCards.test.tsx`, `hypothesisAddress.test.tsx`,
  `pictureHypotheses.test.tsx`, `receiverPlayback.test.tsx`, `hypothesisScreen.test.tsx`,
  `hypothesisEvidence.test.tsx`.
- **The screen (11–12 October):** `lib/affectedArea.ts`, `components/em/EmStatusPill.tsx`,
  `measurements/mutation/mutate_hyp001_003.{py,log}`; `screens/hypotheses.tsx` rewritten;
  `lib/api.ts` (`fetchHypotheses`, `fetchHypothesis`, `HypothesisNotFoundError`),
  `lib/hypothesisVocabulary.ts`, `MapView.tsx` (`bounds`), `App.tsx` (three loaders), the
  map stand-in in `test/setup.ts`; `qa.md` §164.
- **The verdict (13 October):** `alembic/versions/0011_feedback_verdict_known.py`,
  `tests/test_api_feedback.py`; `app/db/hypotheses.py` (`Verdict`, `VERDICT_STATUS`,
  `record_verdict`), the schema's `VerdictRequest`, the route's `post_feedback`; `qa.md` §165.
- **The verdict card (13–15 October):** `test/hypothesisVerdict.test.tsx`,
  `measurements/mutation/mutate_fbk001_002_hyp004.{py,log}`; `screens/hypotheses.tsx` (`VerdictCard`,
  replies held per explanation), `lib/api.ts` (`postVerdict`, `VERDICT_NOTE_LIMIT`),
  `lib/hypothesisVocabulary.ts` (`VERDICT_COPY`, `verdictLabel`, `VERDICT_CARD_COPY`), `App.tsx`
  (`recordVerdict`); `hypothesisScreen.test.tsx` (history now in words) and
  `hypothesisEvidence.test.tsx` (the new prop).

**Changed (main ones):**
- **Store:**
  - `app/db/hypotheses.py`: `campaign_ordinal`, `record_campaign_ordinals`, and the readers
    `hypotheses_at_position`, `hypothesis_by_id`, `verdicts_for`, `bundles_with_hypotheses`;
  - `app/db/bundles.py`: `stored_bundles_by_id`;
  - `app/ai/campaign.py`: passes each row's ordinal.
- **Picture:** schema, builder and route; the old `Hypothesis` shape removed.
- **Evaluation:** `app/evaluation/pack.py` (`order`) and `sampling.py` (`draw_rater_subset`).
- **Frontend:**
  - `routes.ts` (`routeFromHash`, `hypothesisHash`);
  - `useCurrentScreen` returns the route;
  - `App.tsx`;
  - `screens/hypotheses.tsx` and `screens/operationalPicture.tsx`;
  - `types/operationalPicture.ts` and the mock.
- **Tests:** `test_api_route_purity.py` admits `app.db.hypotheses`, with the argument.
- **Tooling:** `Makefile`: `ORDINAL_CONFIRM`, and the `docs/spec.jsonl` mount for backend tests.
- **Docs:**
  - `CLAUDE.md` repo map and `DESIGN.md` (status badge);
  - `scoring_rubric.md` change log (2026-10-09, 2026-10-10);
  - `evaluation_harness.md`, `thesis_notes.md`, `measurements/README.md`;
  - `qa.md` §160–163.

## Failed attempts

**My own errors:**
- **`adp-003`'s tests were edited after `6de44da`, inside `75ed33c`.** First, the not-wired-in test
  searched for the substring `receiver_health` and hit the picture's unrelated `_receiver_health`, so
  it now reads imports and enum members. Second, a lint fix (`# noqa: F811` on the imported fixture):
  `make lint | tail` hid the failure behind the pipe and the test commit went ahead.
- **`adp-003`'s tests were proven red only by an `ImportError` at collection.** The structural
  checks (no number invented in the driver, nothing in `app/` importing the feed) have not been shown
  to catch a planted violation; no mutation pass was run (backend item).
- **The first full-suite run for `adp-003` never ran:** I launched `make test-backend-nobuild` from
  `backend/measurements/`, where there is no such target. That cost about a minute of the active
  time.
- **`57c4a0c`, a `test:` commit, also carries the unreviewed `op-002`/`nav-004` code**, because I
  staged `frontend/src` whole. It was pushed, so I left it rather than rewriting `main`. `passes`
  stayed false until `a67daf5`.
- **I told the user run 480 had an explanation without checking.** It has none
  (`unexplainedConclusions: 1`). What the user saw was the first-paint mock's invented card
  flashing, then the real empty list (`qa.md` §162). The mock was emptied as a result.
- **I said the mixed-evidence packs had no single correct answer** (`qa.md` §160). `scn-002` states
  one ("cannot be distinguished"); corrected by appending.
- **I committed `eval-010` as passing after running its tests only natively.** The container did not
  mount `docs/spec.jsonl`. Fixed in `ceb869f`.
- **Test fixtures with wrong assumptions, found after the code:**
  - `api-004`'s fixture assumed the interference bundle is stored first; it is the fault bundle,
    because the reader sorts by window then subject.
  - `api-019`'s endpoint test used the shared fixture's skeletal radio readings, which the picture's
    position reader rejects; the test now deletes them once the bundles are stored.
- **Tests that passed before their code existed, caught and fixed before the test commit:**
  - a `db-012` constraint test (any database error satisfied it);
  - two `api-019` and three `op-002` frontend tests that asserted preserved behaviour.
- **Earlier tests changed because an item retired what they asserted:**
  - `App.test.tsx`, twice: the evidence text, then "No active hypotheses";
  - `pictureHypotheses.test.tsx`: `article` → link;
  - `levels.test.tsx`: severity removed;
  - `operationalPicture.test.tsx`: the mock's card removed.
- **Code slips:**
  - `eval-011`'s answer-sheet call first passed the whole sample, which the builder refuses;
  - `build_pack`'s inner `order` shadowed the new parameter (caught by mypy).
- **Two greps/awk ranges printed explanation text into the session** while checking packs. Neither
  linked to an arm.

- **Hypotheses screen tests fixed after the test commit `e9baeda`** (my test errors, not screen
  defects):
  - nine map tests queried the map's region before the explanation had loaded;
  - one bounds test rounded 60 km to 0.539° of latitude (it is 0.53899°) and missed by 0.00001°.
- **Two premature passes** among the screen tests (the screen imports no mock; the map opens on the
  corpus by default), folded into failing tests before the test commit.
- **Layout defects found only in the browser:**
  - the map column fell below the whole list at 1456 px;
  - the map's box was 288 px against MapView's own 320 px minimum, so the map covered the sentence
    under it.
- **Mutation pass, first run, 40 of 42:**
  - *a zone holding only some of the conclusion's receivers* and *the conclusion's hour fetched
    filtered* survived, so two assertions were added;
  - *the window's end lost* was a malformed mutant that broke compilation, counted as killed for the
    wrong reason, and was rewritten.

- **`record_verdict` first failed mypy** (`"Result[Any]" has no attribute "rowcount"`) because it
  executed through the session; it now goes through `session.connection()`, as `record_grounding`
  already did.

- **Verdict card, mutation first run 29 of 31:**
  - *a refusal read as success* survived because the refusal tests' bodies failed the reply's shape
    check anyway. The tests now send an explanation-shaped body; **this edited
    `hypothesisVerdict.test.tsx` after its test commit `27e4d21`**.
  - *the card carried to another explanation* (its `key` removed) survived: a new address always
    shows Loading first, which unmounts the card. The `key` was redundant, so it was deleted and the
    mutant dropped.
- **An existing test changed because the item retired what it asserted:** `hypothesisScreen.test.tsx`
  asserted the stored verdict value raw (`needs-more-evidence`); it now asserts the words.
- **A transient outage of the action-approval check** blocked every command and edit for one turn on
  15 October; the work resumed unchanged on the next.

**Carried from earlier sessions, still true:**
- **Never run `biome format --write` over the frontend**: the tree is not in Biome's format, and a
  wholesale run rewrote about 25 unrelated files once. Format only files you wrote whole.
- **Don't name a callback parameter `window`**; it has broken map tests before.
- **The browser tool's ref-based clicks do not register on this page**; coordinate clicks do.

## Next step

1. **The Hypotheses screen, continued**, spec first, in this order:
   - The screen is complete for the backlog. Its open points are below (layout below 1280 px,
     phone width and keyboard order of the card unchecked).
   - The main store now holds the user's two real verdicts; record more only when the user wants.
   - **Never show the screen to the second rater before their scoring is done**: it names each
     explanation's generator.
2. **Second rater (mid-October).**
   - Hand them `scoring_pack_rater2/hypotheses.md` and `score_sheet2.xlsx` first, and `answer_sheet.md`
     only after their pass one. Never `arm_key.*`.
   - **Before approaching them, the user updates the participant information sheet and the ethics form
     (outside the repo) from 280 values / 90 minutes to 140 values and the measured time.**
   - Then `eval-006`:
     - κ over the 20 double-scored items, with its interval;
     - the user's other 20 items single-rated;
     - mixed-evidence cause correctness reported separately;
     - the user's pass two marked unblinded.
3. **Progress note**: version 13 (`09066cf`) is current. `adp-003` has landed: offer an update
   (the third source, the measurement and its threats, and the phantom aircraft).
4. **Remaining strands** (`qa.md` §165): `api-009`; `anom-003`/`anom-006`/`op-006`; decide on
   `ai-005`/`ai-006`; `ops-001`/`ops-002`.

**Open and unowned:**
- **Hypotheses screen, seen and not changed:** the zone's label covers the RF-04 marker on
  `#/hypotheses/104` (the map's own ranking); below 1280 px the map stacks under the alternatives;
  picking another explanation does not scroll to the top; phone width unchecked.
- **The fallback warning has only been seen in tests**: none of the 20 reviewable rows fell back.
- **The mixed-evidence scenario cannot reach its own correct answer** (the sensor-fault verdict ends
  the ladder before aircraft are consulted). Recorded as a limitation; no item addresses it.
- **`arm_key.*` still sits in `scoring_pack/`.** Moving it to a held-back folder is a plain file move.
- **The run list in `evaluation_harness.md` is a snapshot**: a new campaign would need it updated by
  hand.
- **The page behind the drill-down is not inert** (a screen reader can reach the panel behind the
  dialog).
- **Playback under *All* costs about 25 ms per update in the dev build**; production is unmeasured.
- **The backend does not compress responses** (a five-minute track span under *All* is 1.13 MB).
- **During playback the exception panel still shows the whole hour**, and closing playback leaves the
  hour pinned. Both are by design, and neither was asked about.
- **Stale text:**
  - the evidence panel's unexplained sentence ("built and not kept");
  - "20.7M observations" in seven places (the store holds 15.5M);
  - `_corpus.py`'s id ranges;
  - `thesis_notes.md` misfiled from about line 6900.
- **A fresh database cannot score batches from the screen** until `BASELINE_QUIET_RUNS` is
  re-derived for it.
