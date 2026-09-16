# EM Fusion V1 Implementation Checklist (Scope v2)

Use this as a learning checklist, not a rigid sprint plan. For each step, try the implementation first, keep changes small, run tests, update the README, then ask for review when you want feedback.

Scope v2 changes: three screens only (Operational Picture, Hypothesis Detail, Scenario Control); no TimescaleDB, no WebSockets, no multi-agent, no Isolation Forest; AI hypothesis layer and evaluation harness are now first-class phases; ethics and employer clearance run as a parallel non-code track.

## Working Rules

- Before coding a step, write down the user-visible behavior you are trying to create.
- Write or update a test before polishing the UI.
- Prefer analyst-visible tests over implementation details like CSS class names.
- Keep mock data shaped like the future API response.
- Update `README.md` or the relevant package README whenever setup, scripts, scope, or behavior changes.
- After each step, ask: what would happen if we did the simpler or more general version instead?
- Anything cut from v1 (extra screens, WebSockets, Timescale, multi-agent) goes in a FUTURE.md note, not back into scope.

## Track 0: Non-Code (runs in parallel — start now)

- [x] Submit the project proposal.
- [x] **Confirm with the supervisor that the task-based user study is withdrawn** and that the revised aims and objectives are agreed. The proposal was submitted with it; dropping a stated objective is a conversation, not a silent edit. See the reversal entry in `thesis_notes.md`.
- [x] Confirm with the supervisor or the ethics committee **whether blind rubric scoring by a supervisor or colleague requires ethics approval**. Scoring anonymised machine output is not obviously human-participant research, but the answer decides whether an application is needed at all — and if it is, the 4–8 week wait still applies, so ask now rather than in October.
- [x] **Complete and submit the Student Project Ethics Approval Form, declaring human participants.** Answered `YES` to Q1: the second rater is now a colleague rather than the supervisor, and recruitment plus a designed procedure plus a κ statistic computed *from people* makes this human-participant research even though no personal data beyond the consent record is collected. Stays inside module-level approval — no committee gate, no 4–8 week wait. Draft answers, participant information sheet, consent form and recruitment email are in `docs/ethics_form_answers.md`; the reversal against `proposal_draft.md` TOR 9 is in `thesis_notes.md` and `docs/qa.md` §46. Six decisions owed before signature, listed at the foot of that file — the binding one is **whether one colleague scores or two**, because a third rater invalidates Cohen's κ and needs a change-log entry against the pre-registered rubric.
- [x] Secure the **second blind scorer** and agree their time budget in advance (~30% overlap of 25–30 triads, roughly 45–60 minutes plus a calibration round). The agreement is what sizes the campaign, so get it before fixing N.
- [x] Get written employer confirmation: thesis screenshots, repo visibility (public vs private-with-examiner-access), and — only if the second blind scorer is a colleague rather than the supervisor — their participation.
- [x] Confirm in writing whether the employer requires pre-submission review of EW/GNSS-related material.
- [x] Confirm the employer's position on **data egress to a hosted AI API** — evidence bundles will leave the machine. Fold it into the clearance conversation rather than discovering it after the campaign. Blocks the hosted arm, not the build. **Reopened 2026-08-13.** This was closed on the assessment that the content is "synthetic or replayed open data, so this is expected to be a non-issue". That assessment was wrong on the data-licence dimension, though it may still hold on the employer dimension: OpenSky Data License Agreement §3(i) requires aircraft identifiers to be de-identified for any publication *or other disclosure*, and §3(iii) forbids making the data available to anyone outside the licensee's institute. Open access is not permission to disclose. Sending a bundle carrying real `icao24` or `callsign` to a hosted provider is disclosure to a third party. **Mitigated in the build by `dal-004`** — pseudonymisation at the DAL means no real identifier ever reaches a bundle — so what remains for the clearance conversation is the employer's own position, now with the licence question already answered rather than assumed. See `docs/qa.md` §22.
- [x] Confirm which OpenSky terms govern. The `LICENSE.txt` shipped inside the data tarball is dated **2017-08-24** and is *more permissive* than the terms currently published at `opensky-network.org/about/terms-of-use` (retrieved 2026-08-13), which drop "commercial internal testing" and "government purposes" and add a written-licence requirement for commercial entities and for government and military contractors. §2(iii) makes the current published terms operative, since continued use constitutes assent to modifications. Record both in the manifest with their retrieval dates; cite the current terms, not the shipped file.
- [x] Download one hourly OpenSky state-vector file once, filter to the bounding box, and **archive the extract as Parquet locally — not committed** (`https://s3.opensky-network.org/data-samples/states/YYYY-MM-DD/HH/states_YYYY-MM-DD-HH.csv.tar`, ~120–180 MB, no account needed). **Amended 2026-08-13:** the extract was to be committed, but the OpenSky Data License Agreement §3(iii) forbids making the data available outside the licensee's institute. What is committed is the **manifest** (source URL, hour, download date, licence, attribution, SHA-256 of the original) and a **fetch-and-filter script**, so a fresh clone reproduces in one command once the reader accepts the same licence. `data/opensky/` is gitignored. Licence and attribution were recorded at download time and cannot be reconstructed later — see `docs/qa.md` §21. **Done 2026-08-19:** `states_2022-06-27-12.csv.tar`, SHA-256 `6e0d2278…91e2`; extract 133,634 rows, content checksum `7ce83881…be05`, built by `adp-004`/`adp-005`.
- [x] **Choose the bounding box. Fixed 2026-08-19 at 49–54°N, 3–11°E** (~309,000 km²), covering Schiphol, Brussels, Frankfurt, Düsseldorf, Cologne, Luxembourg and Hamburg. Chosen on **usable event sites** — 263 ~20 km cells carrying ≥ 5 simultaneous aircraft, against a ceiling of 150 scenario runs — because coverage quality failed to discriminate: all eight candidates returned a p99 gap of exactly the 10 s cadence. The same box governs the Phase 4 PMTiles cut. See `docs/qa.md` §25.
- [x] Run the coverage acceptance check on the extract: execute `Normal baseline` against it and confirm no dropouts appear before anything is injected. If they do, move the bounding box — genuine coverage gaps are indistinguishable from injected ones and would make the false-positive rate meaningless. **Done 2026-08-19, ahead of the scenario engine**, by measuring the extract directly rather than by running `Normal baseline` through it — the engine does not exist yet and the box decision could not wait for it. **The check does not pass cleanly, and the residue is carried forward:** 10 of 948 tracks (1.05%) hold a genuine interior airborne dropout, and seven of the ten fall in the 100–300 s band that scenario type 4 will inject into. Mitigation, owed before the type 4 campaign: the generator must refuse those tracks as injection sites, using the coverage report to identify them. Re-run this check as originally written once the scenario engine exists.
- [ ] Define detection latency precisely (simulated scenario time, not wall clock) before any measurement code exists.
- [x] Write and pre-register `docs/scoring_rubric.md` — dimensions, worded 1/3/5 anchors, worked example, calibration procedure, adjudication rule, threats to validity. **Drafted 2026-08-07.**
- [ ] Walk the second rater through Part A of `docs/scoring_rubric.md` and confirm the anchors read clearly to someone outside the project. Revise now if not — after the campaign starts it is frozen.
- [ ] **Record the pre-registration commit hash** of `docs/scoring_rubric.md` immediately before the first scored generation, and cite it in the thesis. This is the whole value of pre-registering; an uncited rubric proves nothing about when it was fixed.

### C4 architecture model (Structurizr)

Feeds the **System Design and Architecture** chapter of `thesis_notes.md`. Non-code and non-blocking, but do the first pass early: a container diagram that is awkward to draw usually means the boundaries are wrong, and that is cheaper to learn now than at Phase 7. Revisit at the end so the thesis shows the architecture *as built*, not as planned — and record any divergence, since the divergence is itself write-up material.

- [x] Write the model as **Structurizr DSL** (`workspace.dsl`) and keep it in the repo under `docs/architecture/`. Text, not a drawing tool — it diffs, reviews, and regenerates, and diagrams that cannot be regenerated go stale silently. **Written 2026-08-08**; `docs/architecture/README.md` carries the runbook, and `validate` exits 0.
- [x] **Level 1 — System Context.** EM Fusion as one box. External actors and systems: the analyst, the archived OpenSky corpus, the hosted AI provider, the host-resident local model server. This diagram is where the decision-support framing shows: the analyst is the terminal node, not the system. **Amended:** the local model server is *excluded* from this level — see the Level 2 note. The basemap tile source is not here either, because it is now self-hosted and therefore internal. The hosted AI provider is consequently the only system EM Fusion reaches over a network, which is exactly the claim §10 and §12 make.
- [x] **Level 2 — Containers.** React dashboard, FastAPI backend, PostgreSQL/PostGIS, the local model server as a *host process* rather than a Compose service (per `em_fusion_v2.md` §10). Show polling on the frontend-to-backend edge — the absence of a push channel is a deliberate decision and should be visible. Modelled the host process as an *external system* plus a deployment view, since C4 has no way to draw "container, but outside the deployment boundary". **Amended: the local model server is excluded from L1 and L2 and appears only at L3 and in the deployment view.** Drawing it beside the analyst and the OpenSky corpus overstated it — it is an implementation detail of the hypothesis service that fires only when the hosted API is unreachable, not something the system depends on in the ordinary case. It stays in the model because §12 commits to a two-step degradation the architecture has to be able to explain, and because the UI must surface *which* generator produced a hypothesis. "Silent" means *does not interrupt the analyst*, never *undisclosed*. A fifth container appears here instead: the self-hosted basemap tile archive.
- [x] **Level 3 — Components (backend only).** Adapters, DAL, baseline and anomaly engines, evidence bundle builder, the provider-agnostic hypothesis service with its three generators, repositories, API routes. This is the level that carries the RQ1 extensibility argument: the adapter/DAL seam and the generator seam should be legible as seams. Both seams are tag-styled to stand out; schema validation and the grounding check are separate components rather than one, because the grounding catch rate is a reportable per-arm result.
- [x] **Skip Level 4 (Code).** C4 treats it as optional and it rots fastest; the type definitions and `docs/em_fusion_v2.md` §9 already serve that purpose.
- [x] Render with **Structurizr Lite via Docker** rather than the hosted service — no account, consistent with the project's stance that the hosted AI generator is the sole hosted dependency. The hosted structurizr.com workspace is a fallback if Lite proves awkward, not the default. **Amended:** the standalone `structurizr/lite` image is superseded by the consolidated `structurizr/structurizr` image with a `local` subcommand. Runs on host port 9090, because 8080 belongs to the backend dev server. `theme default` is omitted deliberately — it fetches from a cloud service with a September 2026 EOL, which would defeat the point of a regenerable model.
- [x] Export PNG/SVG for the thesis, and note in `thesis_notes.md` where the model diverges from the planned architecture in `em_fusion_v2.md` §7. **PNG/SVG is a browser-UI action** — the Docker build refuses it ("not supported in this build"). Mermaid/PlantUML/JSON export from the CLI works and is what keeps the figures regenerable; all four views export clean.

**Divergences from `em_fusion_v2.md` §7 found by drawing it** (the first-pass value the note above predicted — write these up in `thesis_notes.md`):

- §7 shows the pipeline as one linear flow and does not distinguish process boundaries. Drawing it forced the question of what runs *when*: the scenario runner and evaluation harness are a batch entrypoint into the same image as the API, not part of the request path, and the container diagram has to say so.
- §7 has no analyst-feedback edge back into the AI layer, and correctly so — but the absence is only legible once drawn, and it is the clearest single statement that this is decision support and not a learning loop.
- The **basemap tile source qualified the "sole hosted dependency" claim** in §10, and the §12 claim that the data and map layers have *no hosted dependency at all*. MapLibre needs no token, but the tiles still come from somewhere, and "tokenless" is not "self-hosted". **Resolved: self-host.** A vector basemap for the project bounding box, served as a static PMTiles archive by the frontend's existing nginx — no tile-server process, no account, no cost. Both claims become literally true, and the demo becomes genuinely offline. Implementation lands in Phase 4; see the amended items there.

**Revisit at the end of the project — the architecture as built, not as planned:**

- [ ] **Reconcile `workspace.dsl` against the finished system.** Walk every container, component, and external dependency in the model and confirm it still exists, is still named the same, and still connects to what the diagram says it does. Delete what was cut, add what appeared, rename what drifted. Diagrams fail silently — an out-of-date one still renders perfectly — so this is a deliberate pass, not something that happens by noticing.
- [ ] **Pay particular attention to what was dropped.** The local generator is time-boxed and droppable; the third source adapter may or may not land; the tile archive may end up as a placeholder. Anything cut in practice but still drawn is the most misleading kind of error, because it shows an examiner a capability that was never built.
- [ ] **Record the divergence between this pass and the model as first drawn on 2026-08-08**, in `thesis_notes.md`. The divergence is the write-up material: an architecture documented once at planning time and never revised is a weaker artefact than one whose revisions are on record. Re-export the figures afterwards.

## Phase 1: Frontend Foundation — DONE

- [x] Create the Vite React TypeScript app in `frontend`.
- [x] Install Tailwind, Vitest, and Testing Library.
- [x] Wire Tailwind into Vite.
- [x] Add `npm test` and `npm run test:watch`.
- [x] Add Testing Library setup for Vitest.
- [x] Replace the starter smoke test with an analyst-visible test.
- [x] Build the smallest operational-picture UI that passes the first test.
- [x] Remove remaining unused starter assets.

## Phase 2: Contract-First Mock Data — DONE

- [x] Identify the operational-picture fields the UI needs for lesson one.
- [x] Extract the current inline scenario data into a small mock data module.
- [x] Define TypeScript types for the operational-picture contract.
- [x] Update the test to prove the UI renders from the mock contract.
- [x] Add one extra assertion only if it represents analyst value.
- [x] Update README with the contract-first mock data approach.

## Phase order — amended

**Phase 5 now runs before the Phase 3 view filter and the Phase 4 playback.** The layout items in
Phase 3 are design-driven and gain nothing from a backend, so they proceed first. But `api-007` (view
filter) and `api-008` (`track-window`) are **server-side by specification**, and building them against
a mock means building them twice:

- The suppressed counts that keep the "+n nominal hidden" footer truthful only exist once the backend
  is doing the filtering. A client-side filter has nothing to report.
- `track-window`'s server-side bound and truncation reporting have no mock equivalent at all.

Revised order: **Phase 3 layout → Phase 5 contract mirror → Phase 3 view filter → Phase 4 MapView →
Phase 4 playback.** Phase 5 is small — `/api/v1/operational-picture` returning the mock shape from a fixture,
a contract test, and the `api.ts` seam that `App.tsx` was already structured for. Everything after it
is built once, against a real fetch.

## Phase 3: Operational Picture Layout (3-screen model)

*Layout items below run first. The view filter subsection waits for Phase 5.*

- [x] Add a left navigation shell with only three sections: Operational Picture, Hypotheses, Scenario Control. **Landed 2026-09-13** (`nav-001`). The route is the **URL hash**, not a router library and not component state, so each entry is a real link that survives a reload and carries `aria-current="page"` on an anchor; an unrecognised hash resolves to the Operational Picture. All three destinations render: Hypotheses names itself unbuilt until `hyp-*`, and Scenario Control is now reachable. The picture poll moved into the Operational Picture's route so it stops when the analyst leaves it. Ten tests, and an eight-mutation pass in place of the coverage the frontend does not measure. **Amended 2026-09-13** (`nav-003`): the rail collapses to a 56px icon rail and back, at the analyst's choice, remembered per browser in guarded `localStorage` rather than in the hash -- the hash says where you are, rail width says how you like your chrome. Icons ride on the route declaration so the three screens stay declared once. Twelve more tests, eleven mutations, and a width transition written and removed after the browser showed it left the rail stuck at 280px.
- [ ] Improve the top status bar using the design tokens from `DESIGN.md`; include data-mode badge, scenario badge, and a compact system-health strip (not a screen).
- [ ] Create a map placeholder component with aircraft, RF sensor, and anomaly-zone labels.
- [ ] Add RF observations and aircraft tracks as panels/tabs inside the Operational Picture — not separate screens.
- [ ] Keep the map library behind a future `MapView` boundary rather than spreading map logic through the app.
- [ ] Add a timeline strip with two or three scenario events.
- [ ] Test the main analyst story, not the exact layout mechanics.

### View filter (specs `op-007`, `api-007`, amends `op-004`)

Added after the original checklist was written. The exception-first default stands — anomalous-only is still what the analyst sees first — but judging an anomaly usually means seeing it against nominal traffic, and forcing that contrast to be inferred is a worse failure than a busier map.

**Build this after Phase 5, not before.** See the phase-order note above: the filter is server-side by specification, so building a client-side version first means building it twice and throwing the first away.

- [ ] Add a three-state view filter — `Anomalous only` / `Nominal only` / `All` — defaulting to anomalous-only.
- [ ] One control drives the map and the exception panel together. They must never disagree about what is shown.
- [ ] Leave drill-down tables unfiltered. They are the show-everything view by definition.
- [ ] Filter server-side via a `view` query parameter, not by fetching everything and discarding client-side. Phase 5 is now built first, so this goes straight into the backend — no mock shim.
- [ ] Carry per-collection suppressed counts in the response. Once the backend filters, the excluded rows never arrive, so the "+n nominal hidden" footer can no longer be computed from the payload — this amends the panel built above.
- [ ] **Adopt TanStack Query here, not before.** Decided 2026-09-05: `api-003` polls one endpoint from one screen with a forty-line hook, and a data-fetching library earns nothing against that. This subsection is the trigger — a second polled endpoint, two consumers of overlapping requests, and a selection that must survive poll ticks are the problems the library exists to solve. `src/lib/api.ts` stays the fetcher either way, so the swap touches the hook and nothing else. Rationale in `docs/qa.md` §42.
- [ ] Test: the selection persists across poll ticks rather than resetting to the default.
- [ ] Test: the hidden count stays truthful when the backend filtered, not zero.

## Phase 4: MapView Boundary

- [ ] Install MapLibre GL JS only when the placeholder no longer teaches enough. (MapLibre, not Mapbox — no account or token needed; see `em_fusion_v2.md` section 10.)
- [ ] **Self-host a vector basemap; do not point at a tile provider.** Vector rather than raster, because the style is written client-side from the `DESIGN.md` tokens — a raster basemap ships whatever colour scheme its renderer baked in, and bright standard-OSM tiles under a dark operational picture compete with the anomaly overlays the screen exists to make salient. Vector also gives continuous zoom and upright, collision-managed labels.
- [ ] Cut a **PMTiles** archive covering the same bounding box as the OpenSky extract — **49–54°N, 3–11°E**, fixed 2026-08-19 (Protomaps build of OpenStreetMap). A single file served over HTTP range requests by the frontend's existing nginx — **no tile-server process and no new Compose service**. A one-box extract is tens of MB rather than the ~100 GB planet file.
- [ ] **Self-host the glyphs and sprites too.** A vector style references fonts and icons by URL, and the default styles point them at a CDN. Miss this and the hosted dependency you just removed comes back silently, with the map still rendering perfectly.
- [ ] Record the **ODbL attribution requirement** ("© OpenStreetMap contributors") at download time, alongside the OpenSky licence note, and render it on the map. Same rule as the corpus: licence terms cannot be reconstructed later.
- [ ] Decide whether the `.pmtiles` archive is **committed or downloaded once against a checksum**. The OpenSky Parquet is committed for reproducibility; the basemap is less critical because `MapView` degrades to a placeholder without it. Tens of MB in git is not free — pick deliberately and write down which.
- [ ] Add `.env.example` entries for the tile archive path/URL and confirm the placeholder path still works when they are unset.
- [ ] Create a small `MapView` adapter component — the only file that imports the map library.
- [ ] Show a graceful placeholder if no tile source is configured.
- [ ] Mock `MapView` in React tests.
- [ ] Manually verify the real map in the browser.
- [ ] Record the diff size for the boundary — it is a cheap second data point for the RQ1 substitutability argument (`thesis_notes.md`).

### Playback (specs `op-008`, `map-004`, `api-008`)

Added after the original checklist was written — a static snapshot cannot show *where* track continuity broke, so playback is what makes a dropout legible as an event rather than a missing row. Build it after the `MapView` boundary exists, never before: playback that reaches around the adapter would undo the substitutability argument the boundary is there to make.

- [ ] Add a playback transport to Operational Picture: play, pause, speed, scrub — over **simulated** scenario time, consistent with the Track 0 latency definition. Never wall clock.
- [ ] Render aircraft at the interpolated cursor position with a trailing path; anomalous track segments visually distinct; anomaly zones appear and clear as their windows enter and leave the cursor.
- [ ] Buffer spans of positions ahead of the cursor and interpolate client-side. **The request rate must not be coupled to the frame rate** — this is what keeps playback inside the no-WebSockets decision rather than quietly reopening it.
- [ ] Add the backing time-window query (`GET /api/v1/aircraft/track-window`), bounded server-side so an over-long span is rejected or truncated with the truncation reported, never silently served in full. Phase 5 is built first, so buffer from the real endpoint — the bound and the truncation report have no mock equivalent.
- [ ] Test: a track whose buffer has not yet loaded holds its last known position and is marked stale — it must not jump to a default coordinate or vanish.
- [ ] Test: the same cursor renders the same data at 1x and 4x. Playback speed must not alter the simulated time of a rendered position.

## Phase 5: FastAPI Contract Mirror

**Runs before the Phase 3 view filter and Phase 4 playback** — see the phase-order note above. *(Amended 2026-09-04: this phase was written expecting a static fixture, because when it was planned there was no database to read. Persistence and the replay landed first, so `api-002` serves real rows instead — a run and 412 live aircraft positions — and the four sections with no producer are served empty rather than filled with a fixture. Serving a fixture would have meant writing the endpoint twice and putting invented data on an analyst's screen in the meantime.)*

- [x] Create the smallest FastAPI app with `/api/v1/health`.
- [x] Add a backend test for `/api/v1/health`. *(`api-001` passes: 5 tests, 100% coverage. Route lives in `app/api/v1/health.py` behind the `api_router` prefix.)*
- [x] Add `/api/v1/operational-picture` returning the same shape as the frontend mock data. *(**`api-002` passes 2026-09-04** — 24 tests, 323 passed at 99.89%, plus 7 frontend tests. Serves the run and its final-window positions from PostGIS, not a fixture. Live against the development database: run 8, 412 tracks, 58 KB, ~0.40 s warm.)*
- [x] Add a backend contract test for the response shape.
- [x] **Guard against fixture/type drift.** *(Done as a backend test that parses `operationalPicture.ts` and compares field sets in both directions, with `frontend/src/types` mounted read-only into the test container. Mutation-tested: a field added to the TypeScript side alone turns exactly one parity case red.)* *(Original wording:* The backend fixture and the frontend `OperationalPicture` type describe the same contract in two languages and will diverge silently unless something forces them together. Assert the same shape from both sides — a backend contract test plus a frontend test that parses a copy of the real response — so a field renamed in one place fails a test rather than surfacing as an empty panel.*)*
- [x] Connect the frontend to the endpoint behind a small `api.ts` function (simple fetch/polling — no WebSockets in v1). *(**`api-003` passes 2026-09-05** — `src/lib/api.ts` is the only module that reaches the network, `src/hooks/useOperationalPicture.ts` owns the 5 s poll and the degraded flag, and `App.tsx` was the whole change: no component was touched, which is the contract-first structure paying off. 23 frontend tests, 340 backend. Verified in a real browser against the running stack — five polls at 200 through nginx, the badge appearing when the backend was stopped and clearing when it came back.)*
- [x] Keep the mock fallback until backend integration is stable. *(Kept, with a change of meaning: the mock is the fallback only while nothing real has ever arrived. After a successful poll the last real payload is retained instead, because reverting measured data to invented data on a network blip is a downgrade in honesty as well as usefulness. The app reports itself degraded from first paint, since the mock is on screen at that moment.)*
- [x] **Assert that the new route handler holds no SQL, no session, and no spatial logic.** *(**`db-006` passes 2026-09-05** — 13 tests, 336 passed at 99.89%. The check parses; it caught `api-002`'s route importing `sqlalchemy.orm` for a type annotation, fixed with a `SessionFactory` alias in the storage layer. Mutation-tested both ways: a real query turns three assertions red, the same text in a docstring turns none — while `grep -c` on the same file returns 1.)* *(`db-006`, split from `db-003` on 2026-09-02 — the enforcement half of FR-904. It belongs here rather than in Phase 6 because there is nothing for a handler to bypass until this endpoint exists. The check parses the route modules; a substring match over their source is satisfied by an example in a docstring, which is how the equivalent check in `dal-004` failed once already.)*

**Phase 5 complete, 8 of 8, 2026-09-05.** Written up in `docs/thesis_notes.md` — the phase narrative, the contract-first seam scored with its diff (4 files, 118 insertions, of which 101 are two new modules; the screen's data-consuming code untouched), and the three limitations it leaves behind.

## Phase 6: Persistence (PostgreSQL + PostGIS)

- [x] Add PostgreSQL + PostGIS via Docker Compose (backend + db services now; frontend service can join in Phase 11). *(Done 2026-08-13, ahead of this phase — the `frontend` service landed at the same time rather than waiting. `postgis` 15/3.5 on a named volume, health-gated, `DATABASE_URL` passed to `backend` and `pipeline`. Nothing connects to it yet: that is `db-005`.)*
- [x] Connect to it: engine, session, and configuration. *(`db-005` passes 2026-08-28 — 21 tests, `app/db/session.py` at 100%. One `Engine` per process built in `app.main`'s lifespan and disposed on shutdown, a `sessionmaker` bound to it, and a per-request `Session` dependency that rolls back on exception. Construction opens no connection, so the unit suite still needs no database.)*
- [x] Create the core schema: observations, track/RF/source-health payloads, anomaly events, hypotheses, analyst feedback. *(`db-001` passes 2026-08-29 — 22 database tests, 205 passed with a live PostGIS. **Seven** tables, not six: `quarantined_records` was added when the ERD was found to have no home for the records `dal-002` requires.)*
- [x] Include the reproducibility columns on `hypotheses` now: `generator` (`template|local|hosted`), `model_id`, `generation_params`, `raw_response`. *(Done in the first revision. `generator` and `confidence` also carry CHECK constraints — confidence is Low/Medium/High and the database will not hold anything else.)*
- [x] Add a repository layer: the PostGIS implementation of the DAL's port. *(**`db-003` passes 2026-09-02** — 20 tests, `app/db/repository.py` at 100% in the container, 252 passed. The port signature survived unchanged; the prediction is scored in `thesis_notes.md`. The schema is reflected rather than redeclared, which is what GeoAlchemy2 earns its place doing, and the `geometry` warning filter came out in the same change.)* *(`db-003`. The command surface is ready: `ops-003` passes 2026-08-30, so `make test` now starts PostGIS, provisions `test_em_fusion` and runs the database tier — 232 tests in the container. **Split 2026-09-02:** the "and keep SQL out of route handlers" half is now `db-006` and moves to Phase 5, because it cannot be proved before a data-serving route exists.)*
- [x] A committed way to replay the corpus end to end. *(**`adp-007` passes 2026-09-04** — `python -m app.replay` plus `make replay`. Full corpus into PostGIS: 133,634 read, 133,134 accepted, 500 quarantined, 12 batches, **14.25 s** when first measured and about 9.8 s over three runs against a warm stack on 2026-09-04 — the figure is condition-dependent, see `thesis_notes.md`. `ops-003` green again with the target added.)*
- [x] Mark a scenario run complete, so a partial run is distinguishable from a finished one. *(**`db-007` passes 2026-09-04** — revision `0002_scenario_run_completion`, a `complete_scenario_run` function in the storage layer, and `app.replay` marking its run after the final batch commits. 10 tests across three files, four mutations recorded, 288 passed at 99.87%. Verified on the development database: the run that predates the column stayed null, the new one recorded `completed_at - started_at` of 9.765 s against a self-reported 9.75 s. Null means not known to have finished, which falls out of `adp-007`'s per-batch unit of work — an interrupted replay keeps its committed batches, and re-running starts a new run rather than resuming, so partial runs accumulate looking exactly like complete ones.)*
- [x] Implement at least one real spatial query (track discontinuities within N km of an RF anomaly zone) — this is the PostGIS justification. *(**`db-004` passes 2026-09-15.** Built in Phase 8, where it is first needed: `anom-004`, `anom-005` and `anom-007` all name it, and there are no discontinuities to query for until `anom-010` produces them. Left unticked here until it lands.)*
- [x] Add a migration approach and document it. *(Alembic, revisions hand-written, autogenerate off. Documented in `README.md`; rationale and the rejected alternatives in `thesis_notes.md`.)*
- [x] Backend tests run against a disposable test database. *(A `database` marker plus `TEST_DATABASE_URL`; the fixture drops and recreates `public` per test so every migration test starts from genuinely empty. Skips when the variable is unset, so the unit tier still needs no Docker.)*

## Phase 7: Scenario Generator and Adapters

**Order within this phase, settled 2026-09-05: `scn-005` first, then `scn-001` with the first seeded
emitter, then `scn-002`'s types.** The identifiers suggest starting at `scn-001`, and that is the
wrong way round. `scn-001` is a *property* — same type, parameters and seed give a byte-identical
stream — and proving it requires a stream to prove it over. The stream comes from the scenario types,
which emit through the synthetic RF adapter, which reports on a sensor and channel grid that does not
exist yet. `normal-baseline` cannot stand in as the minimal case either: it injects nothing by
definition, which is what makes it the false-positive control, so determinism over it is nearly
vacuous. `scn-005` is the one item here with no dependency on the others — a fixed layout is pure
configuration with no randomness in it — so it goes first, and `scn-001` lands with the smallest
seeded emitter that actually has something to be deterministic about. See `docs/qa.md` §43.

- [x] Fix the RF grid as configuration before writing the generator (spec `scn-005`): six to eight sensors at recorded positions, eight 2 MHz channels centred 1567.42–1581.42 MHz with one channel exactly on GNSS L1. Position sensors so a candidate interference zone contains some and excludes others — otherwise `anom-005` and `anom-007` have nothing to discriminate. **Done 2026-09-05:** seven sensors at Dutch and German airfield positions inside the corpus bounding box, loaded from `backend/app/scenario/rf_layout.json` and validated on load. FR-109 is enforced as two invariants at a 70 km radius — every sensor has a neighbour within it and a non-neighbour beyond it — which hold across a measured band of [55.7, 85.7) km. Detector radii for `anom-005` and `anom-007` should be chosen from that band.
- [x] Stage only on aircraft in flight (`scn-006`). *(**`scn-006` passes 2026-09-16** — 4 tests, 763 passed at 99.91%, five mutations all caught including the one that moves the gate below the answer-key write. The targeting asked whether an aircraft was inside the zone and nothing else, so **209 of 381 aircraft the answer key called staged were parked for every report of the run** — 55% of every injection landing where nothing could be detected, and `anom-010` refusing them correctly. Measured on a second independently seeded batch: parked aircraft in the key fall from 55% to 2%, and recall rises from 25% to **69%**, 81% for `gnss-degradation`. **The prediction attached to this item was falsified.** Clustering still does not separate a staged run from its control — +0.05 to +0.40 on the largest group, 1 to 3 of 20 triples — because the fix raised recall by shrinking the denominator, not the numerator: detected staged findings per run went 1.2 → 1.4 against a background of 15.5. The limiting quantity is how many aircraft a run stages on, and that is now the open question. One cost: 10 of 40 runs stage nothing at all, against 3 of 80 before.)*
- [x] Build a parameterised scenario generator: scenario type + parameters (noise amplitude, gap duration, sensor count, area, timing, seed). **Done 2026-09-12** (`scn-003`, in two passes): per-run seeds and corpus windows derived from one base seed, the run row made able to regenerate its own stream, and `execute_run` driving both halves of a run under one id. `make generate` works for the first time — measured at 20 runs, 52.5 s, ~510k rows, 0–11 aircraft staged per run. Two defects found by running it rather than by testing it: a stale pipeline image (the one target with no build prerequisite) and a batch whose incident started after its runs ended, which produced twenty mislabelled controls reporting `ok`. **Half done 2026-09-07:** the baseline emitter and its `RunSpec` landed with `scn-001` — nominal power, noise spread and nominal SNR over the layout's full grid. Gap duration, affected area and event timing arrive with `scn-002`'s types, which is where the parameters stop being baseline-shaped.
- [x] Every run is reproducible from its seed and parameters — this is the foundation of the evaluation harness. **Done 2026-09-07** (`scn-001`): values are derived per cell from the seed and the cell's coordinates rather than drawn from a seeded sequence, so traversal order is not an input. Verified byte-identical across macOS/arm64/py3.14 and Linux/aarch64/py3.13, and mutation-tested — a generator that ignores its seed leaves 20 of 21 tests green, and one derived through Python's salted `hash` leaves 19. Detail in `docs/qa.md` §47.
- [x] Implement adapter 1: replayed OpenSky telemetry from the archived file. *(`adp-001`, and end to end through `adp-007`. Ticked 2026-09-13 — the box outlived the work.)*
- [x] Implement adapter 2: synthetic RF observation generator under scenario control, emitting on the full sensor × channel × time grid. Every sensor reports every channel every interval, so a missing reading is a detectable gap rather than an ambiguous absence. **Done 2026-09-11** (`adp-002`): `app/adapters/synthetic_rf.py` is a driver only — it plans the run's incident from the spec, so a caller cannot store a quiet grid under a run row claiming interference, and builds its own ingest context, so no caller can mark a synthetic run replayed. The unit of work is one run rather than one window, deliberately the opposite of `adp-007` and for a reason that reverses on this side: a synthetic run regenerates from its seed, so all-or-nothing costs nothing to retry. Measured: 5,040 readings of a fifteen-minute run stored in 0.45 / 0.44 / 0.43 s, all 5,040 cells distinct in the database. Five mutations, all red.
- [x] Add spectral extent as a **parameter** of `gnss-degradation` — narrowband confined to the L1 channel, or broadband across the grid. Not a sixth scenario type. **Done 2026-09-11** (`scn-002`): a dial on both interference types, asserted by a closed-set test over the five members that goes red the moment a sixth is added.
- [x] **Ground truth never leaves the run record** (spec `api-009`). Assert it: no observation, anomaly, bundle, or API response carries the scenario type or injected event for a scorable run. A detector that can see the answer invalidates every metric. **Done 2026-09-11** (`scn-002`): `Incident` carries no scenario type, so the emitter cannot label a reading with what produced it; `signal_type` is identical on staged and quiet readings; and `ScenarioRunSummary` has no field capable of holding the answer key. Re-assert as anomalies, bundles and hypotheses arrive.
- [x] Implement the DAL: canonical observation model, required-field validation, quarantine of malformed records, provenance attached to every record. *(`dal-001` through `dal-003`, in Phase 2. Ticked 2026-09-13.)*
- [x] Pseudonymise aircraft identifiers **at the DAL** (`dal-004`), not per adapter — deterministic from a configured seed so track continuity survives, source values discarded rather than kept alongside, no readable reverse mapping. Build it with `dal-001`, before `adp-001` replays a single real row: retrofitting it after a campaign means every stored observation, bundle, and hypothesis carries a real identifier that has to be migrated out. *(Done, and before `adp-001` replayed a row, as this item asked. Ticked 2026-09-13.)*
- [ ] Move GNSS degradation data into a scenario fixture; add a normal-environment fixture for comparison.
- [ ] Test: malformed records are quarantined, valid records land in the canonical store with provenance.

## Phase 8: Baseline, Anomaly Detection, and Evidence Bundles

**Order within this phase, settled 2026-09-14: `anom-002` first, then `anom-001`, then the new
`anom-010`, then `db-004` — and only then the fusion rules.** The identifiers mislead here in the
same way they did in Phase 7, and for the same reason: `anom-001` names the baseline from `anom-002`
as one of its inputs, so the item numbered first consumes the item numbered second. A threshold rule
with nothing to be a threshold against is not a smaller version of the rule; it is a different one.

Three corrections were made to the backlog on picking the phase up, each recorded in `docs/spec.jsonl`:

- **FR-304 had no spec item.** Nine `anom-*` items covered eight of the nine detection requirements.
  `anom-004` clusters track-continuity anomalies and `anom-006` consumes track dropout clusters, and
  nothing in the backlog produced one — the rule the whole fusion pair rests on was the one rule
  nobody had written down. Now `anom-010`, and it inherits the corpus-dropout problem below.
- **`db-004` is a Phase 6 leftover that Phase 8 depends on.** It is the last unticked item of that
  phase — the real spatial query that justifies the spatial database — and `anom-004`, `anom-005`
  and `anom-007` all name it. It is built here, in this chain, rather than left behind a phase
  boundary that no longer reflects what depends on it.
- **`anom-002`'s per-channel claim cannot be proved on quiet data.** Measured against the twenty
  normal-baseline runs: 56 sensor-channel cells, 1,800 samples each, cell means spanning 0.177 dB.
  A pooled baseline is indistinguishable from a per-cell one there, so the test proving the
  granularity has to be built from staged runs, not from the baseline corpus.

Two items do not sit in the sequence at all. **`anom-008` accumulates rather than lands**: its own
text requires correct non-detection to be asserted for every detector, not once in aggregate, so a
case is added as each detector arrives and the item closes when the last one does. And **`anom-009`
is gated on Track 0**, which still owes a precise definition of detection latency *before* any
measurement code exists — the entire value of that item is that it is settled first.

**The corpus-dropout conflict is the one thing to settle before writing tests.** `normal-baseline`
replays real corpus traffic, and the coverage check of 2026-08-19 found 10 of 948 tracks carrying a
genuine interior airborne dropout, seven of them in the same 100–300 s band scenario type 4 injects
into. So `anom-010` will fire on a run `anom-008` requires to be silent. The resolution is the
exclusion already owed by Track 0 — the generator refuses those ten tracks as corpus-window content
— extended from injection sites, where it was owed, to baseline windows, where it is equally needed
and had not been noticed. Raising the threshold past 300 s would buy a clean false-positive rate by
blinding the detector to the injected band; relaxing `anom-008` would mean a false-positive control
that permits known firings.

- [x] Implement the baseline engine (rolling averages over normal-scenario runs), **per sensor per channel** for RF metrics. Pooling channels into one per-sensor baseline hides single-channel deviations inside the spread of the others. *(**`anom-002` passes 2026-09-14** — `app/detection/baseline.py`, 27 tests, 100% on the module, 613 passed at 99.88% in the container. Mean, sample standard deviation and sample count per sensor-channel cell over a trailing window, with an explicit insufficient-data result rather than an average over one point. **Scope narrowed to RF metrics**: the item also asks for track metrics per region, no region concept exists, and nothing consumes a track baseline — recorded on the item, and the engine is written per cell so that half is an extractor rather than a rewrite. Two design points worth carrying forward: the caller names the quiet runs and anything else is refused, because an observation carries no scenario type for the engine to recognise staged data by; and the window is a trailing duration ending at the newest observation rather than at the wall clock, since a replayed hour from 2022 has no relationship to the time now. Eleven mutations, ten caught — the eleventh is an equivalent mutant, see `thesis_notes.md`.)*
- [ ] Implement deterministic detectors only: threshold rules, z-score deviation, spatial clustering. No Isolation Forest in v1. *(**Threshold rule done: `anom-001` passes 2026-09-14** — `app/detection/rf_noise.py`, 28 tests, 100% on the module, 641 passed at 99.89% in the container, fifteen mutations all caught. Episodes per cell rather than one anomaly per reading, since a run emits 5,040 readings. The comparison carries a **direction per metric** — power upwards, SNR downwards — because an absolute deviation reports a channel quieter than its baseline as noise, and staged interference only ever pushes the metric one way, so no run in the corpus would have exposed it. A cell with no usable baseline is reported unjudged rather than skipped, which is what keeps `anom-008`'s control meaningful. **Spatial clustering done: `anom-004` passes 2026-09-15** — `app/detection/clustering.py`, 16 tests, 100% on the module, 740 passed at 99.90% in the container, eleven mutations caught and the twelfth verified equivalent. **Its premise was measured before it was written, and failed.** Over eight seed-matched triples the largest cluster on a staged run equals the largest on its own control in all eight at every radius 5–20 km, and findings per run are 15.9 staged against 16.0 control — clustering track gaps cannot tell a staged run from a quiet one. The control is an `rf-sensor-fault` run at the same seed, not a `normal-baseline` one, because no baseline run in the batch shares a seed with a staged run. So the output is rescoped to an **intermediate finding**, the radius is explicitly **not fitted**, and `anom-011` was written for the real cause: `TRACK-GAP` recall is 21%, flat across every policy parameter swept, and a background cluster sits within the fusion radius on **70% of sensor-fault runs**. **`anom-011` gates `anom-005`, `anom-006` and `anom-007`** — built first, all three would pass their unit tests on fixtures and fail together at evaluation. Still to come here: `anom-003` z-score.)*
- [x] Implement the local rate excess (`anom-012`) and rewire `anom-005` onto it. *(**`anom-012` passes 2026-09-16** — `app/detection/rate_excess.py`, 12 tests, 775 passed at 99.91%, ten mutations all caught. Replicated out of sample on a third batch before being built; pooled over 40 pairs all three radii separate at p = 0.047, 0.006, 0.001. No threshold and no default radius: that choice belongs to `anom-013`.)* **Route B, chosen 2026-09-16 after measuring both routes.** Cluster size carries no signal; the replacement asks whether dropouts are more frequent at a place during a window than at the same place outside it, so each run is its own control on both axes. Measured over 20 seed-matched pairs: at 30 km it catches 5 of 20 staged runs and fires on 2 of 20 controls; at 60 km, 16 of 20 and 9 of 20. **The gain is in false attribution, not sensitivity** — the fusion rule as specified would have misattributed 70% of sensor-fault runs, and this cuts that to 10% at 30 km. The difference-in-differences form was implemented, measured, and dropped: identical separation, more machinery. **Route A — raising the 8% affected fraction until clusters stand out — was rejected**, because a parameter chosen by searching for a value where the detector succeeds makes every later metric a measurement of that search.
- [x] Settle the ordering between `anom-005`, `anom-006` and `anom-007` before fixing any threshold. **Settled as `anom-013` on 2026-09-16, specced and unbuilt:** `anom-007` first on the RF pattern alone, then `anom-006`, then `anom-005`. The three partition one decision rather than testing independently, and a zone claimed by an earlier rule is not offered to a later one — which makes `anom-006`'s existing mutual-exclusion constraint enforceable rather than aspirational. Deciding the fault first removes the 70% misattribution rather than answering it with the weaker signal. `anom-007` separates a sensor fault from interference on the **RF pattern alone** — one sensor abnormal, neighbours clean — which is stronger than any track evidence measured. If it claims those runs first, `anom-012`'s threshold is read from the sensitive end of its curve rather than the specific end. Never written down.
- [x] Implement the track-continuity rule, `TRACK-GAP` (`anom-010`, FR-304) — position staleness beyond a configured threshold. Nothing else produces the discontinuities `anom-004` clusters and `anom-006` discriminates on. *(**`anom-010` passes 2026-09-14** — `app/detection/track_gap.py`, 28 tests, 100% on the module, 669 passed at 99.89% in the container, seventeen mutations all caught. **The corpus-dropout assumption this line was written with was wrong by two orders of magnitude**, and measuring before writing corrected it: the background is ~138 aircraft per quiet run, not ten tracks, and no threshold separates staged GNSS degradation from it — above 600 s the quiet runs are higher. So the output is an **intermediate finding** feeding `anom-004`, and `anom-008` was amended to count only the fused reportable types. Two mechanisms, since the two scenario types stage differently; frozen position additionally requires fresh contact, which cuts the background from 137.7 to 24.6 per run at no cost to the staged margin. Airborne and interior filters remove four fifths of the raw findings. Detail in `thesis_notes.md` and `docs/qa.md` §62–63.)*
- [x] Implement the PostGIS spatial query (`db-004`) — track discontinuities within N km of an RF anomaly zone in a window, distance computed on geography by the database rather than in Python. Carried over from Phase 6, where it is the last unticked item. *(**`db-004` passes 2026-09-15** — 15 tests, 703 passed at 99.90% in the container. **Blocked, then unblocked, the same day.** It had nothing to query: `anomalies` had never been written to or read, no item covered doing so, it could not hold a point-located finding, and it carried no run id at all. **`db-008` passes 2026-09-14** — a `detection_findings` table with a Point location and a GiST index, one canonical finding shape every rule becomes, and a write that replaces per run per rule. Picking `db-004` up then found that it and `anom-004` describe **different queries**, and that `db-001`'s own comment misnames it: `db-004` is the proximity query FR-905 asks for, and clustering is now **`db-009`** — written rather than left as a note, which is the lesson FR-304 taught earlier in this phase. Two findings from building it: the window test is **overlap, not containment**, because a gap that began before the window opened is still happening during it and `anom-005` is looking for exactly those; and `ST_DWithin` on geography is **not inclusive at the boundary** — measured, against an item that had claimed it was from documentation — so the radius is bracketed to metre precision instead. An `&&` bounding-box prefilter is what lets the GiST index assist, asserted by a plan test rather than assumed.)*
- [x] Implement PostGIS clustering of findings (`db-009`) — `ST_ClusterWithin`, not `ST_ClusterDBSCAN`: scope v2 excludes DBSCAN, and it would need a minimum-points parameter nothing here has a basis for choosing. Transitive closure is a recorded limitation — a chain of findings can form a group far wider than the radius that produced it. *(**`db-009` passes 2026-09-15** — 21 tests, 724 passed at 99.90% in the container, **ten mutations all caught, the first clean pass of the phase**. Four assumptions in the item did not survive contact with the database. `ST_ClusterWithin` has **no geography overload** at all — both signatures take geometry and a distance in the SRID's own units — so the item's central constraint was unsatisfiable as written; resolved by projecting to EPSG:3035, measured at **2.57 m of error on a 5 km radius** across the corpus box against the ~62% a radius in raw degrees would cost. The **window form** `ST_ClusterWithinWin` is used rather than the aggregate, which returns geometry collections and loses row identity. And determinism failed at the **fifteenth significant figure**: `ST_Centroid` sums in the order `ST_Collect` assembled, floating-point addition is not associative, and re-inserting the same findings moved a centroid by 8e-15 degrees — about 0.9 nanometres, physically nothing and enough to break NFR-601. Fixed by ordering the window frame, so summation order is a property of the query rather than of the heap; the test catches the unordered form 3 times in 3. Detail in `thesis_notes.md` and `docs/qa.md` §64.)*
- [ ] Add a simple rule that explains why the GNSS hypothesis exists (RF deviation + clustered track gaps, same window and area).
- [ ] Test each detector with both degraded and normal scenarios — a correct non-detection is a first-class test.
- [ ] Add the frequency-adjacency test to the sensor-fault rule (`anom-007`), recorded as evidence distinct from the spatial-neighbour test. A single anomalous channel with clean neighbours on the same sensor points at the sensor; a deviation across all eight points at the environment.
- [ ] Build the evidence bundle builder: grouped anomalies, source lineage, rule IDs, known uncertainties. Group on **three** axes — time window, spatial proximity, **frequency adjacency**. Grouping on time and space alone fragments one broadband event into eight unrelated findings.
- [ ] Test: every evidence item in a bundle traces to a stored anomaly/observation.

## Phase 8.5: AI Layer Prerequisites (gate — settle before writing model code)

None of this blocks the **template generator**, which is the first thing built in Phase 9 and needs no model at all. It gates the two *model* arms. The point of a gate is that these are all cheap now and expensive-to-impossible after a campaign has run.

**Decisions to fix and write down (no code):**

- [ ] Choose the hosted model and **pin a dated model ID, not a moving alias**. An alias changing mid-campaign invalidates the comparison with no visible failure.
- [ ] Choose the local model and quantisation; confirm it loads on the host and emits schema-valid output. **Time-box this to about a day.** The local arm is the availability fallback and offline-demo guarantee only — it is not scored, and nothing downstream depends on it. If it fights you, cut it, let the template generator be the sole fallback, and record that the offline demo shows template output.
- [ ] Fix generation parameters once — temperature 0, seed, max tokens — and freeze them across arms. Different params across arms make the comparison meaningless.
- [ ] Decide **N generations per bundle per arm**. This multiplies both cost and campaign wall-time, and drives the grounding-variance measurement. Pick it deliberately, not by drifting upward.
- [ ] Decide the **total spend ceiling** for the project and the expected campaign cost within it.
- [ ] Fix the blind-scoring corpus — **hosted-vs-template only**, a stratified sample of ~20 evidence bundles (5 per anomalous scenario type), 40 hypotheses, fully double-scored. The local arm is not scored. Fix before M9; adjusting after seeing results is a validity problem, not a scheduling one.
- [ ] Confirm the Track 0 data-egress item is closed.

**Implementation prerequisites (build before the first real call):**

- [ ] Define the provider-agnostic service interface (`evidence_bundle → validated hypothesis`) **before** either provider is written, so neither provider's shape leaks into it. Provider, model ID, and params come from config.
- [ ] API key in an environment variable with a `.env.example` entry — never committed, never in a fixture.
- [ ] **Hard spend cap set at the provider console.** Do this before the first call, not after the first surprise.
- [ ] **Run-level call budget in the code** that aborts the run when exceeded. The console cap is the backstop; this is the thing that catches a retry loop in minutes rather than at the billing boundary.
- [ ] Bounded retry with an explicit ceiling and no unbounded recursion — the realistic route to an unexpected bill is a loop bug, not the campaign.
- [ ] Per-call logging of tokens and cost from the very first call. Retrofitting this loses the development-phase spend data that makes the campaign estimate credible.
- [ ] Verify the `hypotheses` reproducibility columns from Phase 6 exist and are actually populated end to end.
- [ ] Verify the backend container reaches the host model server via `host.docker.internal` — Docker Desktop on macOS does not pass Metal through, so the model server runs on the host as a Compose config value, never as a Compose service.
- [ ] Smoke-test on **3 bundles before scaling to any batch** — read the output by hand. Cheapest possible check that the prompt and schema are right.

## Phase 9: Constrained AI Hypothesis Layer (RQ3 — core deliverable)

- [ ] Define the hypothesis output schema in Pydantic (title, confidence Low/Medium/High only, summary, supporting evidence, uncertainty, alternatives, recommended action).
- [ ] Build the template-based hypothesis generator first — it is the correctness fallback *and* the evaluation baseline. No model dependency; nothing in Phase 8.5 blocks it.
- [ ] Implement the hosted AI generator (primary arm) using native JSON-schema-constrained output, so schema conformance is a generation-time guarantee rather than a post-hoc check.
- [ ] Implement the local AI generator (second arm) against the *same* schema via a GBNF grammar. One schema, two enforcement mechanisms, identical guarantee.
- [ ] Persist `generator`, `model_id`, `generation_params`, and verbatim `raw_response` on every hypothesis, both arms.
- [ ] Implement the two fallbacks as **separate** paths and keep them separate in code: **availability** (hosted unreachable → local) and **correctness** (schema/grounding failure after bounded retry → template).
- [ ] Implement the automated grounding check: every supporting-evidence item must trace back to the bundle; flag or reject ungrounded hypotheses; log the catch rate **per arm** (this is a reportable result).
- [ ] Keep confidence as Low, Medium, or High — no fake numerical precision. The constrained schema should make anything else unrepresentable rather than merely rejected.
- [ ] Surface the producing generator in the UI — a hypothesis produced by a fallback must be visibly distinguishable, not silently substituted.
- [ ] Test with mocked responses: valid output passes; invalid output retries then falls back to template; hosted-unreachable falls back to local; ungrounded claims are caught.
- [ ] **Exercise the offline path deliberately** — network off, no API key, full pipeline still produces hypotheses via the local arm. The section 12 reliability claim now rests entirely on this, and an untested fallback is an unbacked claim.
- [ ] Update README with the constrained-AI design, the three generators, and why the arrangement is safer.

## Phase 10: Analyst Feedback and Scenario Control

- [ ] Add analyst actions: confirm, reject, needs more evidence, false positive.
- [ ] Add a note field only after the action flow works.
- [ ] Persist feedback in the database; submitting feedback changes hypothesis status (test this end to end).
- [ ] Build the Scenario Control screen: start, pause, reset, replay; select scenario type and parameters. **The screen landed 2026-09-13** (`scn-004`): scenario library, the configuration form, the run controls, the status indicator and the recent-runs table, with 22 screen tests and 8 contract-parity tests. What is left here is the wiring, and it is `api-006`'s: the controls render **disabled, with the reason on screen**, because no endpoint starts a run. **Pause is not built** — `FR-806` provides no endpoint for it and a batch of whole runs has nothing to pause; it belongs to `FR-717`'s playback transport (`op-008`), and the divergence from `FR-714` is recorded in the spec item. The screen became **reachable in the browser** on 2026-09-13 at `#/scenario-control` (`nav-001`). **Wired the same day** (`api-006`, `api-010`): the runs come from `GET /api/v1/scenario/runs` on the five-second poll, `START BATCH` posts to `POST /api/v1/scenario/start` and names the base seed the server used, and the fixture is retired along with the sentence that described it. `RESET` and `REPLAY` stay disabled and say why -- reset has no endpoint (deferred by `api-006`), and a single-run replay is not a request `start` can make, since a batch is between 20 and 30 runs.
- [ ] Explain in README that this is decision support, not autonomous decision-making.

## Phase 11: Evaluation Harness (build before October, not during)

- [ ] Batch runner: execute 20–30 randomised runs per scenario type from parameters + seeds.
- [ ] Compute precision, recall, F1, false positive rate, false negative rate, and detection latency (in simulated time, per the Track 0 definition).
- [ ] Export results to CSV/JSON for thesis tables and charts.
- [ ] Generate hypotheses from the **hosted and template** generators over identical bundles, anonymised for blind rubric scoring (per the Phase 8.5 decision). The local arm is exercised as a fallback but is not scored.
- [ ] Emit the scoring pack: rendered hypothesis pairs in randomised order, identical formatting across arms, arm key held in a separate file, plus a blank score sheet per rater.
- [ ] Ingest completed score sheets; compute per-dimension means per arm and quadratic-weighted Cohen's κ across the double-scored corpus. Apply the pre-registered adjudication rule for disagreements.
- [ ] Produce N generations per bundle per model arm; record grounding catch rate, grounding variance, and retry rate **per arm**. Keep this separate from rubric scoring — raters see one generation per arm, not all N.
- [ ] Record actual campaign cost and wall-time per arm — both are write-up material, and the cost figure is what makes the "deliberate spend" claim in `thesis_notes.md` concrete.
- [ ] Late-project extensibility demonstration: add a third source adapter and record files touched, lines changed, and hours taken (RQ1 evidence).
- [ ] Dry-run the full evaluation once in early October before the real runs.

## Phase 12: Docker, CI, and Polish

**Partially pulled forward to 2026-08-13.** The container work was scheduled here but happened during
Phase 5, because developing an API seam against a stack that has to be started by hand is slower than
building the stack. What landed early is listed below; CI genuinely remains, and that is the item that
turns these commands from a convention into an enforcement.

- [x] Route the whole stack through a root `Makefile` — one command surface over Compose (`make` lists
      the targets). Adapted from an earlier project; the `ensure-artifacts` guard came with it and is
      deliberately empty, because this project commits its corpus and regenerates synthetic data from a
      seed. See `thesis_notes.md`.
- [x] Add `scripts/smoke-test.sh`: a post-start check that the services can reach *each other*, not
      merely that each answers. Both containers can report healthy while the path between them is
      broken — which is exactly what happened twice while writing the Compose file.
- [x] Pin backend dependencies. `pyproject.toml` plus a committed `uv.lock`; tool config consolidated
      into the same file (ruff replaced flake8 and isort, which removed the last config file that could
      not live there).
- [x] Run the frontend container unprivileged (`nginx-unprivileged`, uid 101, port 8080).

- [x] Extend Docker Compose to run frontend, backend, and database together. *(Done 2026-08-13. `make up` starts all three with `depends_on: service_healthy` gating; `make smoke` asserts the frontend→backend proxy hop and that PostGIS initialised.)*
- [ ] Add CI for frontend tests/build and backend tests.
- [x] Add linting checks. *(Done 2026-08-13, but **locally only** — `make lint` runs ruff over the backend and Biome over the frontend, `make check` chains format → lint → type-check → test. These are the commands CI will call; nothing enforces them on push until the item above lands.)*
- [ ] Basic dependency audit only — no further security tooling in v1. *(Now possible: `backend/uv.lock` pins the full graph, where the previous requirements files pinned nothing.)*

## Review Prompts

- [ ] Can I explain this change back in plain English?
- [ ] Did I add only the files needed for the current behavior?
- [ ] Did I run tests before asking for review?
- [ ] Did the README change if the project behavior or setup changed?
- [ ] What tradeoff did I choose, and what did I postpone?
- [ ] Does this change serve an evaluation result or a research question — or is it just a feature?
