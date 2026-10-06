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

It closed with **six decisions taken and specced, none of them built**. Those are the next session's
work and they are set out under *Next step*. Nothing is in flight; read that section first.

## Current state

Backlog **83 of 117**. Three items landed and the code for a fourth; two items were then added and
four amended, which is why the passing count moved less than the work did.

| | |
|---|---|
| `db-011` | A bundle a hypothesis cites may not be replaced. **Green.** |
| `api-015` | `GET /api/v1/operational-picture/evidence?run=N`. **Green.** |
| `op-010` | The panel. Built and green — then **amended to be collapsible**, so it is back to `passes: false` with only that one constraint outstanding. |
| `evb-003` | The pass stores what it builds — **green**. The corpus-wide fill — **superseded**, see below. |
| `anom-017`, `api-016` | New, specced, unbuilt. |
| `op-004`, `op-006`, `api-007` | Specced before, **amended this session**, unbuilt. `op-006` was passing and is now `false`: its strip moves into a tab. |

**Two items are marked `passes: false` with working code behind them** (`op-006`, `op-010`), because
an amendment added a constraint neither satisfies yet. That is deliberate — the flag tracks the spec
as written, not the code as it stood when it was written.

- Backend: **2040 passed, 99.93% coverage, exit 0**, in containers (1957 at the start).
- Frontend: **236 passed** (203 at the start), Biome clean, `tsc -b` clean. Still no coverage
  tooling on that side, which is what the mutation pass is for.
- `make lint`, `make format`, mypy clean (80 source files).
- Mutation, one pass over all four items, **32 of 32 killed, no survivors, none equivalent**:
  `mutate_api015_evidence.log` (19 backend, 13 frontend). The first run left **five gaps and all five
  were real** — see Failed attempts.
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

### Decided, 6 October: pin it, then re-score

`anom-017` carries both. The population is **all 100**, and that choice is measured rather than
preferred — checked before specifying:

- the 60-run set is a **strict subset** of the 100 (set difference empty);
- **every one of the 100 is corpus v2** by `scn-008`'s base-seed discriminator, and all are 900 s.

So this is one homogeneous population measured twice, once with 40 fewer runs — not two populations
to choose between. More of the same data is a better estimate of normal and nothing measured argues
the other way.

Four things `anom-017` requires, and the order is part of it:

1. **Pin** the ids as a constant in `app/detection/settings.py` beside the other eleven settings. A
   run named in the constant but absent from the store is a **refusal**, not a quietly smaller
   baseline.
2. **Re-score** every completed run under it — its own script, its own confirm variable. Unlike
   `evb-003`'s fill, which refuses on disagreement, a changed claim is the **expected** outcome here
   and is **recorded**: the log must name *which* runs moved, before and after, because that count is
   the result.
3. **Re-run `detection_metrics.py`** and re-commit its log. It re-runs the detectors rather than
   reading `detection_findings`, so the re-score does not invalidate its figures — it leaves them
   taken under a baseline the store no longer has, which is worse.
4. **Report the delta.** Do not let it quietly supersede the old log.

**Which figures are at risk, concretely.** Detection figures are quoted **15 times** in
`thesis_notes.md` and the progress note carries **21 instances of `1.000`**. Recall (60 of 60) and
precision (1.000) should hold — the injected incident sits well above threshold by construction, so a
20-second shift in a window boundary does not change whether a run is caught. **Latency is the figure
that moves**, because it is onset-to-detection and the boundary that shifted is the term it measures.
Current medians: 10 s on both fault arms, 20 s on interference.

`evb-003`'s fill is **superseded** by the re-score, which stores every bundle on every run as a side
effect of re-scoring. `backfill_bundles.py` stays committed with its log, since the stop is the
finding that produced `anom-017`.

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
| `5a2e86b` | `docs: the evidence panel — notes, Q&A, repo map and handoff` |
| `918431e` | `measure: mutation pass over db-011, api-015, op-010, evb-003 — 32 of 32` |
| `a54bc83` | `spec: add anom-017, api-016; amend op-004, op-006, api-007, op-010` |

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

**New, measurements** — `measurements/mutation/mutate_api015_evidence.py` + `.log`.

**Requirements** — FR-720, FR-812, FR-907, AC-14, and from the spec work NFR-605, FR-721, FR-813,
AC-15. **Q&A** — 149, 150, 151.

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


**The mutation pass found five gaps and every one was real.** Four items landed on a suite I had
thought complete.

| Survivor | What it was |
|---|---|
| three on the frontend fetch | **`loading` and `failed` were the same state.** The panel said *the evidence could not be loaded* while a fetch was in flight — false at the moment it is shown — and with the two merged, each of the hook's two mechanisms satisfied the test alone, so neither could be shown load-bearing. The five states are now named and `undefined` is gone from the contract. |
| one more, after that fix | Removing the clear-on-hour-change. My loading test only **mounted**, and the hook's initial state is already loading, so the clear could not be told from the initial value. |
| a group's span | `min(started_at)` → `members[0]` survived, because the builder emits a group's items in time order so *first* **is** *earliest* on every fixture. |

And one apparent survivor that was **not** one: `unclaimed = [` → `unclaimed = [] or [` is equivalent,
since `[] or [x]` is `[x]`. The harness's own validity check cannot catch that — the file parses and
the text differs — so an equivalent mutant reads as a gap. Replaced with one on the comprehension's
filter, which is killed.

The two orderings lesson generalises and is now recorded twice: **a guard against stale state is
killed only by a test that supplies stale state on purpose**, which is `anom-015`'s ordering rule in
another costume.

**Two existing tests asserted the contract `evb-003` reverses.** Rewritten with their reason rather
than deleted — `test_storing_the_bundles_is_the_callers_call` and the *built and not stored* block.

**The backend image build failed once on `uv sync --locked`** and succeeded on retry with no change.
Transient; recorded so the next occurrence is not investigated from scratch.

**A test asserted a count that the run id already contained.** `"2" in message` on a refusal naming
run 8812. Strengthened to `"3 hypothes"`, which pins the number and the noun.

## Next step

**Everything below was agreed on 6 October and none of it is built.** Six pieces, in this order.
Three of them are a chain where nothing is visible until the last lands.

| | | gated by |
|---|---|---|
| 1 | **`anom-017`** — pin the baseline, re-score the corpus, re-measure, report the delta | — |
| 2 | **`api-016`** — each aircraft track carries the state this run's findings put it in | — |
| 3 | **`api-007`** — server-side view filter with suppressed counts | `api-016` |
| 4 | **`op-007`** — the Anomalous / Nominal / All control | `api-007` |
| 5 | **`op-004`** — the tabbed exception panel, absorbing `op-006`'s timeline | `op-007` |
| 6 | **`op-010`** — the evidence panel becomes collapsible | — (small, independent) |

Start with `anom-017`: it makes the store consistent before anything else reads it, and it is the
only piece that writes to all 400 runs.

### The three findings that shaped the panel specs

**The Tracks tab had no producer at all** — not a thin one, none. `AircraftTrack` carries `id`,
`name`, `altitudeFt`, `lat`, `lon`. *Tracks (3 degraded)* would have put an invented number in a tab
label, which is `api-002`'s producer-less field reaching an analyst rather than sitting empty.
`api-016` gives it one, with **three states and not two**: a track on an hour nobody examined is
`unknown`, never nominal — `api-012`'s distinction again. The state is **`interrupted`**, not
`degraded`: the finding is that an aircraft's reporting broke, and *degraded* is a judgement about
the aircraft that nothing makes. `op-004`'s tab label was amended to match — **the label follows the
producer, rather than the producer being renamed to fit the label.**

**An empty tab says what it found.** The default filter is *Anomalous only*, so on a quiet hour all
three tabs are empty — and a table with no rows above a footer reading *+7 nominal sensors hidden*
states the hidden count twice and the finding not at all. Each tab renders a sentence instead. That
is `op-003`'s dash-versus-sentence correction at its **third** site.

**The Events tab absorbs the Timeline** rather than sitting beside it. One list rendered twice is the
drift the single copy module exists to prevent, one layer up. The rail drops to hypothesis cards and
the detection summary, which is what FR-707 actually asks for.

**The reading order this produces**, worth keeping as the screen grows: **where** (map) → **what is
exceptional** (the tabs) → **what it means** (the rail) → **why** (the evidence panel).

### Three things I asked and did not get an answer to

Carried forward rather than assumed:

1. **Scope.** Six items is larger than the four just done, and items 3–5 are a chain where nothing is
   visible until the last one lands. The alternative offered was to stop after `anom-017` + `op-010`
   — the store made consistent and the evidence panel finished — and take the panel chain as its own
   session.
2. **Running the re-score**, as against only building its script. It writes to all 400 runs. The plan
   is to dump the three tables first, as this session did, and to log the before/after of every claim
   that moves.
3. **`op-005`'s drill-down tables** — the *View all* link's destination — are **not** in the six. The
   plan is to render the link disabled with a reason, as `RESET` and `REPLAY` are on Scenario
   Control, unless it should come too.

### Then, unchanged

7. **The map** (`map-001`–`map-004`). Largest, specced, unblocked — and `op-007`'s filter is
   specified to drive the map and the panel *together*, so building the panel first leaves that half
   of its failure case vacuous until the map exists.
8. **`hypotheses`**, the last producer-less field. 155 rows exist.
9. **`eval-006`** still waits on a second rater.

Open and unowned:

- **A figure quoted 7 times across the docs is stale.** `CLAUDE.md`,
  `docs/phase8_evidence_bundles.md` and `docs/qa.md` argue from "20.7M observations"; the store holds
  **15.5M**. It sits inside the grounding-check tractability argument, so it wants correcting
  deliberately rather than by search-and-replace.
- **The progress note has not been updated for this session.** The evidence panel is a new stage of
  the pipeline spine and the first thing on the screen that answers *why*. Worth doing **after**
  `anom-017`, not before: the re-score may move the latency figures it quotes.
- ~~Four bundles' windows disagree with their claims.~~ Cause understood and remedy decided:
  `anom-017`'s re-score rewrites every run under the pinned baseline, which takes these with it.
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
- Nothing mechanical stops a **third** file declaring its own eleven detector settings. `anom-017`
  adds a twelfth to the module, so the test pinning the count needs updating with it.
- **`_corpus.py`'s id ranges are stale.** Its docstring says runs 1–240 are corpus v1, and the
  base-seed discriminator says every quiet run from 21 to 400 is v2 — the corpus was regenerated
  after the loss and the ids were reused. The discriminator is right and the prose is not; nothing
  depends on the prose, which is why it has survived.
