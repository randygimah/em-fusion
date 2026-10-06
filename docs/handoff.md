# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session ran 4–6 October 2026 and took **item 4 of the agreed screen sequence — serve an
evidence bundle, so the screen can say *why***. It was not specced at the start. It is now four
items, three of which are built and green.

The screen stated a conclusion and gave no route to what it rests on, which is the project's own
subject. The account already existed one layer down, with every absence typed and every citation
resolved. What did not exist was an endpoint, a panel, and — found while specifying — a guard
without which the obvious implementation deletes the scored campaign.

## Current state

Backlog **85 of 115**. Three items landed; `evb-003` is half built and its other half is blocked on
a decision that is not a code decision (see *The baseline*, below).

| | |
|---|---|
| `db-011` | A bundle a hypothesis cites may not be replaced. **Green.** |
| `api-015` | `GET /api/v1/operational-picture/evidence?run=N`. **Green.** |
| `op-010` | The panel. **Green.** |
| `evb-003` | The pass stores what it builds — **green**. The corpus-wide fill — **blocked**. |

- Backend: **2039 passed, 99.93% coverage, exit 0**, in containers (1957 at the start).
- Frontend: **232 passed** (203 at the start), Biome clean, `tsc -b` clean. Still no coverage
  tooling on that side.
- `make lint`, `make format`, mypy clean (80 source files).
- **No mutation pass was run this session.** Three were run last session; this one spent its time on
  four items and a corpus investigation instead. `op-010` is a frontend item and therefore has no
  coverage figure behind it — a pass over it is the first thing owed.
- The store is **byte-for-byte as it was at the start**: 400 runs, 103 bundles, 8306 findings, 155
  hypotheses, 20 runs at the 100-run baseline. Verified after a partial fill was restored from a dump.
- **A Vite dev server is running on `localhost:1234`** (IPv6 only — use `localhost`). Kill it with
  `pkill -f "em-fusion/frontend.*vite"`. The container on `:8080` serves the pre-session bundle until
  `make build-frontend`.

### What the screen does now

Under the picture, full width, an **Evidence** panel. Verified against the real store on four hours:

| Hour | What it shows |
|---|---|
| 420 (newest, staged) | one conclusion, named as having no stored evidence |
| 400 (quiet) | nothing was reported, so there is nothing to explain |
| 41 (fault) | 4 evidence groups, 3 typed absences, the neighbours marked as judgements |
| 102 (interference) | 8 radio deviations with their peaks, the rule's reasoning, the aircraft-side ratio, **9 discontinuities across 8 aircraft collapsed to one sentence**, two absences |

## The baseline, and why the fill stopped

**The store holds detection findings written under two different baselines, and nothing on the
screen or in `eval-002`'s table says which.**

| `BASELINE.quiet_run_count` | Runs |
|---|---|
| 60 | **378** |
| 100 | 22 |

`measure_normality` takes `quiet_run_ids` — every quiet run the store holds — so the normality a run
is scored against depends on how large the store was when the pass ran. `anom-016` named this hazard
when it put the quiet runs on the record (*two baselines under identical thresholds give different
findings and are otherwise indistinguishable*), and `eval-003`'s policy column is what made it
visible. Neither prevents it.

The fill found it at run 71 of 144: the rebuilt claim's window begins at 12:22:13 where the stored
one begins at 12:22:33, with identical thresholds. It stopped rather than skipping, which is
deliberate — a skip would have rewritten 139 further hours under settings just shown to differ.

**It inverts a reading made earlier the same day.** Four bundles whose windows disagree with their
claims were recorded as *stale*. They are not: run 71's bundle, written 19 September, agrees with
today's rebuild to the second, and it is the stored **finding** that came from the other baseline.

**The decision this waits on is the user's**, and it is one of:

1. Re-score the corpus under one baseline — uniform store, but every detection figure of record is
   rewritten and `detection_metrics.py` must be re-run and its log re-committed.
2. Leave two baselines and **report** which is which, wherever a figure is quoted.
3. Pin the baseline population explicitly rather than taking it from the store, so the variable
   stops moving — which is a new spec item and does not fix the 400 runs already scored.

## Files in flight

None. The tree is clean.

## Changed

| Commit | Message |
|---|---|
| `d080269` | `spec: add db-011, api-015, op-010, evb-003 — the screen says why` |
| `b92e859` | `test: add tests for db-011` |
| `ae15aba` | `feat(db-011): a bundle a hypothesis cites may not be replaced - tests pass` |
| `7d14e3c` | `spec: amend api-015, evb-003 — there is no key joining a bundle to its claim` |
| `1a7ee5a` | `test: add tests for api-015` |
| `876f51e` | `feat(api-015): the screen can ask why - tests pass` |
| `a777268` | `test: add tests for op-010` |
| `86cad93` | `feat(op-010): the conclusion says why - tests pass` |
| `c9394da` | `test: add tests for evb-003` |
| `7cbfd2a` | `feat(evb-003): the pass stores the account it builds - tests pass` |

**New, backend** — `app/api/v1/schemas/evidence.py`, `tests/test_db_cited_bundles.py` (17),
`tests/test_api_evidence.py` (44), `tests/test_evb_persisted.py` (12),
`measurements/corpus/backfill_bundles.py` + `.log`.

**New, frontend** — `src/types/evidence.ts`, `src/components/em/EmEvidencePanel.tsx`,
`src/hooks/useEvidenceAccount.ts`, `src/test/evidencePanel.test.tsx` (20),
`src/test/evidenceAccess.test.tsx` (9).

**Changed** — `app/db/bundles.py` (`db-011`), `app/detection/chain.py` (stores bundles, first),
`app/detection/control.py` (`reportable_keys`), `app/detection/findings.py` (`claim_identity`),
`app/api/v1/operational_picture.py`, `app/api/v1/schemas/operational_picture.py`,
`src/lib/api.ts`, `src/lib/detectionVocabulary.ts`, `src/App.tsx`,
`src/screens/operationalPicture.tsx`, `Makefile` (`BACKFILL_CONFIRM`),
`tests/test_api_route_purity.py` (allowlist + argument), `tests/test_anom_chain.py` (two
assertions rewritten), `tests/test_api_hour_selection.py`, `src/test/dataAccess.test.tsx`,
`src/test/hourSelection.test.tsx`, `src/test/systemStatus.test.tsx`.

**Requirements** — FR-720, FR-812, FR-907, AC-14. **Q&A** — 149, 150, 151.

## Failed attempts

**I specified a key that misses half the corpus, and only measurement said so.** `api-015`'s first
draft matched a bundle to its claim on the subject. A fusion bundle's subject is the receivers that
deviated together, joined; the claim is filed under the first of them. 41 of 103 bundles would never
have matched — and every fault would have, so it works on half a corpus, which is the shape of a
defect that looks like a feature.

**Then I over-corrected.** The second draft dropped the subject entirely, on the measured ground that
a four-field key matched the same 99 of 103. It does, and it cannot attribute a bundle on a run
holding two faults in one window — which occurs zero times here and is entirely legitimate. Reading
the two **constructors** rather than the rows settled it: the relationship holds by construction, not
as a property of this corpus.

**I called four bundles stale and they were not.** Recorded in the spec, in `qa.md` §151 and above.
A disagreement between two stored records says which pair disagrees and nothing about which is right,
and the intuition that the older artefact is the stale one is wrong here.

**`evb-003`'s ordering constraint was wrong, twice.** First: *bundles after the findings they cite* —
citations resolve against **observations**, written at generation time, so there is no dependency at
all. Then: *the fill writes bundles and only bundles* — two rules read stored track findings back, so
a pass that writes no findings cannot reach the fusion decision. Both withdrawn and replaced in the
open.

**I put the bundle write before the bundles were built.** `UnboundLocalError` across eleven chain
tests. The comment explaining the ordering was correct; the code was above the line it described.

**A fetcher that cast blindly took down four other suites.** `fetchEvidenceAccount` cast the response
to the account type, and every other suite's `fetch` mock answers *any* url with a picture payload —
so the panel read `account.explained.length` on an `OperationalPicture` and crashed the render.
`fetchSelectableHours` already guards exactly this and the rule had not been carried across.

**The proxy-assertion hazard, for the third time, and my search for it missed one.**
`url.includes("operational-picture")` as a stand-in for one endpoint. `op-009` broke it with
`/hours`; this item would have broken it again with `/evidence`. Four files, all now comparing the
exact route — and the fourth was found only by a failing test, because it spells the path as a string
literal rather than importing the constant. **A repo-wide search for a constant finds every use of
the constant and none of the copies.**

**Three defects found by looking at the running screen**, none reachable by a test: an absence
rendered three times identically (real bundles repeat one up to 28 times), the verdict block
repeating the conclusion's own heading two centimetres below it, and *"holds no stored evidence"*.
The first was fixed in the **endpoint**, not the panel.

**Two existing tests asserted the contract `evb-003` reverses.** Rewritten with their reason rather
than deleted — `test_storing_the_bundles_is_the_callers_call` and the *built and not stored* block.

**The backend image build failed once on `uv sync --locked`** and succeeded on retry with no change.
Transient; recorded so the next occurrence is not investigated from scratch.

**A test asserted a count that the run id already contained.** `"2" in message` on a refusal naming
run 8812. Strengthened to `"3 hypothes"`, which pins the number and the noun.

## Next step

1. **A mutation pass.** Four items landed with none, and `op-010` is a frontend item with no
   coverage figure behind it. One harness over `db-011` + `api-015` (backend) and one over `op-010`
   (frontend); the harness dispatches on which suite guards a file, not where the file lives.
2. **The baseline decision**, above. It gates finishing `evb-003`'s fill, and the fill is what gives
   140 hours their evidence — without it the panel is correct and empty on every hour anybody opens.
3. **The map** (`map-001`–`map-004`). Largest, specced, unblocked.
4. **Re-run the figures of record.** Now more pressing: `detection_metrics.py` re-runs the detectors,
   so whatever baseline the store holds when it runs is the one its figures are taken under.
5. **`hypotheses`**, the last producer-less field. 155 rows exist.
6. **`eval-006`** still waits on a second rater.

Open and unowned:

- **A figure quoted 7 times across the docs is stale.** `CLAUDE.md`,
  `docs/phase8_evidence_bundles.md` and `docs/qa.md` argue from "20.7M observations"; the store holds
  **15.5M**. It sits inside the grounding-check tractability argument, so it wants correcting
  deliberately rather than by search-and-replace.
- **The progress note has not been updated for this session.** The evidence panel is a new stage of
  the pipeline spine and the first thing on the screen that answers *why*.
- **Four bundles' windows disagree with their claims** (ids 220, 237, 242, 251 on runs 54, 71, 76,
  105). Cause understood — the baseline — remedy pending the decision above.
- **`api-015` refuses an hour whose store disagrees with itself** in two ways: two bundles or two
  claims sharing a match key. Neither occurs on this corpus, so both paths are unexercised outside
  the suite.
- **0 of 103 stored bundles carry a superseded claim**, so the panel's ruled-out block is unexercised
  on real data.
- **The hour chooser is blind by design**, so finding a staged hour means knowing its number.
- **A pinned hour is not in the URL.** Considered and deferred; it is `nav-001`'s machinery.
- **The evidence account is fetched per hour, not polled.** A pass completing while the screen is
  open does not appear until the hour changes.
- **`docs/thesis_notes.md` is misfiled from about line 6900 onwards.** This session's entries were
  placed in the right chapters.
- Nothing mechanical stops a **third** file declaring its own eleven detector settings.
