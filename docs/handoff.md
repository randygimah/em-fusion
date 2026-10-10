# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session (9–10 October 2026) did four things:

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

Everything went spec → failing tests → code → user review (→ mutation pass for frontend items) →
`passes: true`, committed on `main`.

## Current state

**Backlog 110 of 128.** `main` is in sync with `origin/main`; tree clean once this handoff is
committed.

**Suites:**
- Backend, full container suite: **2,306 passed, 99.90%** (6,045 statements, 6 missed; 15 min 25 s),
  run after the model-id change at a67daf5.
- Frontend: **525 passed**; Biome lint and `tsc -b` clean.

**The main database is migrated to `0010`** and the ordinal copy has run: 80 positions written from
the committed campaign record; a second run wrote 0 and left 80 unchanged.

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
- **The address.** `#/hypotheses/<id>` opens the Hypotheses placeholder, marked current, naming the
  explanation. A malformed id is no id, never a guessed one.
- **Checked in the browser:**
  - run 102's card → `#/hypotheses/76`;
  - run 480 reads "1 conclusion this hour has no explanation yet";
  - run 123 shows the NEW badge;
  - the Detection Summary heading now matches Hypotheses (colour, size, font).
- **The twenty runs with an explanation** are listed in `docs/evaluation_harness.md` ("Where the
  scored explanations are on screen"): 102–118 interference, 123–137 sensor fault, 161–175
  mixed evidence.
- **Mutation:** `mutate_op002_nav004.log`, **22 of 22** on the first run (styling not mutated).

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
Hypotheses screen work** (`db-012` onward).

## Files in flight

None. The tree is clean once this handoff is committed.

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
  `pictureHypotheses.test.tsx`, `receiverPlayback.test.tsx`.

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

**Carried from earlier sessions, still true:**
- **Never run `biome format --write` over the frontend**: the tree is not in Biome's format, and a
  wholesale run rewrote about 25 unrelated files once. Format only files you wrote whole.
- **Don't name a callback parameter `window`**; it has broken map tests before.
- **The browser tool's ref-based clicks do not register on this page**; coordinate clicks do.

## Next step

1. **The Hypotheses screen, continued**, spec first, in this order:
   - **Amend `hyp-001`–`hyp-003`** to the plan decided on 9 October (`qa.md` §157, thesis notes),
     against the design reference `assets/Design/Hypothesis_analysis_v2/`:
     - *keep:* title, confidence, status, window, verdict buttons and note, and the disclaimer;
     - *drop:* the invented sources, uncertainty categories, "Sector A / Zone AZ-402", the satellite
       heat map, and the live-feed chrome;
     - *split:* uncertainty and alternatives into two sections;
     - *add:* summary, recommended action, provenance (the detail half of `ai-010`), a list to choose
       from, verdict history, a not-found state, and a map of the conclusion through `MapView`.
     - The data is already served by `GET /api/v1/hypotheses/{id}`, and the address and placeholder
       exist.
   - **Pin the verdict → status mapping in `api-005`:**
     - confirm → Confirmed;
     - reject → Rejected;
     - false positive → Rejected, with the verdict kept on the feedback row;
     - needs more evidence → Under review;
     - Inconclusive stays in the stored set, unused.

     Then `fbk-001`/`fbk-002`, then `hyp-004` (the disclaimer).
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
3. **Offer a progress-note update** once the Hypotheses screen shows something worth telling.

**Open and unowned:**
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
