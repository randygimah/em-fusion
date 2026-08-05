# EM Fusion V1 Implementation Checklist (Scope v2)

Use this as a learning checklist, not a rigid sprint plan. For each step, try the implementation first, keep changes small, run tests, update the README, then ask for review when you want feedback.

Scope v2 changes: three screens only (Operational Picture, Hypothesis Detail, Scenario Control); no TimescaleDB, no WebSockets, no multi-agent, no Isolation Forest; AI hypothesis layer and evaluation harness are now first-class phases; ethics and employer clearance run as a parallel non-code track.

## Working Rules

- [ ] Before coding a step, write down the user-visible behavior you are trying to create.
- [ ] Write or update a test before polishing the UI.
- [ ] Prefer analyst-visible tests over implementation details like CSS class names.
- [ ] Keep mock data shaped like the future API response.
- [ ] Update `README.md` or the relevant package README whenever setup, scripts, scope, or behavior changes.
- [ ] After each step, ask: what would happen if we did the simpler or more general version instead?
- [ ] Anything cut from v1 (extra screens, WebSockets, Timescale, multi-agent) goes in a FUTURE.md note, not back into scope.

## Track 0: Non-Code (runs in parallel — start now)

- [ ] Submit the project proposal.
- [ ] Submit the university ethics application for the user study (approval can take 4–8 weeks — do not wait until October).
- [ ] Get written employer confirmation: colleague participation, thesis screenshots, repo visibility (public vs private-with-examiner-access).
- [ ] Confirm in writing whether the employer requires pre-submission review of EW/GNSS-related material.
- [ ] Confirm the employer's position on **data egress to a hosted AI API** — evidence bundles will leave the machine. Content is synthetic or replayed open data, so this is expected to be a non-issue, but fold it into the clearance conversation rather than discovering it after the campaign. Blocks the hosted arm, not the build.
- [ ] Download and archive the OpenSky historical dataset once; record licence/attribution requirements.
- [ ] Define detection latency precisely (simulated scenario time, not wall clock) before any measurement code exists.
- [ ] Recruit 3–6 user-study participants by early October.

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

## Phase 3: Operational Picture Layout (3-screen model)

- [ ] Add a left navigation shell with only three sections: Operational Picture, Hypotheses, Scenario Control.
- [ ] Improve the top status bar using the design tokens from `DESIGN.md`; include data-mode badge, scenario badge, and a compact system-health strip (not a screen).
- [ ] Create a map placeholder component with aircraft, RF sensor, and anomaly-zone labels.
- [ ] Add RF observations and aircraft tracks as panels/tabs inside the Operational Picture — not separate screens.
- [ ] Keep the map library behind a future `MapView` boundary rather than spreading map logic through the app.
- [ ] Add a timeline strip with two or three scenario events.
- [ ] Test the main analyst story, not the exact layout mechanics.

### View filter (specs `op-007`, `api-007`, amends `op-004`)

Added after the original checklist was written. The exception-first default stands — anomalous-only is still what the analyst sees first — but judging an anomaly usually means seeing it against nominal traffic, and forcing that contrast to be inferred is a worse failure than a busier map.

- [ ] Add a three-state view filter — `Anomalous only` / `Nominal only` / `All` — defaulting to anomalous-only.
- [ ] One control drives the map and the exception panel together. They must never disagree about what is shown.
- [ ] Leave drill-down tables unfiltered. They are the show-everything view by definition.
- [ ] Filter server-side via a `view` query parameter, not by fetching everything and discarding client-side. Until Phase 5 lands, filter the mock behind the same function signature the API call will use.
- [ ] Carry per-collection suppressed counts in the response. Once the backend filters, the excluded rows never arrive, so the "+n nominal hidden" footer can no longer be computed from the payload — this amends the panel built above.
- [ ] Test: the selection persists across poll ticks rather than resetting to the default.
- [ ] Test: the hidden count stays truthful when the backend filtered, not zero.

## Phase 4: MapView Boundary

- [ ] Install MapLibre GL JS only when the placeholder no longer teaches enough. (MapLibre, not Mapbox — no account or token needed; see `em_fusion_v2.md` section 10.)
- [ ] Pick a free tile source and add `.env.example` with its URL.
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
- [ ] Add the backing time-window query (`GET /aircraft/track-window`), bounded server-side so an over-long span is rejected or truncated with the truncation reported, never silently served in full. Until Phase 5 lands, buffer from the mock.
- [ ] Test: a track whose buffer has not yet loaded holds its last known position and is marked stale — it must not jump to a default coordinate or vanish.
- [ ] Test: the same cursor renders the same data at 1x and 4x. Playback speed must not alter the simulated time of a rendered position.

## Phase 5: FastAPI Contract Mirror

- [ ] Create the smallest FastAPI app with `/health`.
- [ ] Add a backend test for `/health`.
- [ ] Add `/operational-picture` returning the same shape as the frontend mock data.
- [ ] Add a backend contract test for the response shape.
- [ ] Connect the frontend to the endpoint behind a small API function (simple fetch/polling — no WebSockets in v1).
- [ ] Keep the mock fallback until backend integration is stable.

## Phase 6: Persistence (PostgreSQL + PostGIS)

- [ ] Add PostgreSQL + PostGIS via Docker Compose (backend + db services now; frontend service can join in Phase 11).
- [ ] Create the core schema: observations, track/RF/source-health payloads, anomaly events, hypotheses, analyst feedback.
- [ ] Include the reproducibility columns on `hypotheses` now: `generator` (`template|local|hosted`), `model_id`, `generation_params`, `raw_response`. Cheap while the table is empty; a migration plus an un-rerunnable campaign afterwards.
- [ ] Add a repository layer; keep SQL/spatial logic out of route handlers.
- [ ] Implement at least one real spatial query (track discontinuities within N km of an RF anomaly zone) — this is the PostGIS justification.
- [ ] Add a migration approach (even a simple ordered-SQL-files convention) and document it.
- [ ] Backend tests run against a disposable test database.

## Phase 7: Scenario Generator and Adapters

- [ ] Build a parameterised scenario generator: scenario type + parameters (noise amplitude, gap duration, sensor count, area, timing, seed).
- [ ] Every run is reproducible from its seed and parameters — this is the foundation of the evaluation harness.
- [ ] Implement adapter 1: replayed OpenSky telemetry from the archived file.
- [ ] Implement adapter 2: synthetic RF observation generator under scenario control.
- [ ] Implement the DAL: canonical observation model, required-field validation, quarantine of malformed records, provenance attached to every record.
- [ ] Move GNSS degradation data into a scenario fixture; add a normal-environment fixture for comparison.
- [ ] Test: malformed records are quarantined, valid records land in the canonical store with provenance.

## Phase 8: Baseline, Anomaly Detection, and Evidence Bundles

- [ ] Implement the baseline engine (rolling averages over normal-scenario runs).
- [ ] Implement deterministic detectors only: threshold rules, z-score deviation, spatial clustering. No Isolation Forest in v1.
- [ ] Add a simple rule that explains why the GNSS hypothesis exists (RF deviation + clustered track gaps, same window and area).
- [ ] Test each detector with both degraded and normal scenarios — a correct non-detection is a first-class test.
- [ ] Build the evidence bundle builder: grouped anomalies, source lineage, rule IDs, known uncertainties.
- [ ] Test: every evidence item in a bundle traces to a stored anomaly/observation.

## Phase 8.5: AI Layer Prerequisites (gate — settle before writing model code)

None of this blocks the **template generator**, which is the first thing built in Phase 9 and needs no model at all. It gates the two *model* arms. The point of a gate is that these are all cheap now and expensive-to-impossible after a campaign has run.

**Decisions to fix and write down (no code):**

- [ ] Choose the hosted model and **pin a dated model ID, not a moving alias**. An alias changing mid-campaign invalidates the comparison with no visible failure.
- [ ] Choose the local model and quantisation; confirm it loads on the host and emits schema-valid output before committing to it as the second arm.
- [ ] Fix generation parameters once — temperature 0, seed, max tokens — and freeze them across arms. Different params across arms make the comparison meaningless.
- [ ] Decide **N generations per bundle per arm**. This multiplies both cost and campaign wall-time, and drives the grounding-variance measurement. Pick it deliberately, not by drifting upward.
- [ ] Decide the **total spend ceiling** for the project and the expected campaign cost within it.
- [ ] Decide the blind-scoring split — hosted-vs-template at full N, local-vs-hosted as a smaller secondary sample. Fix before M9; adjusting it after seeing results is a validity problem, not a scheduling one.
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
- [ ] Build the Scenario Control screen: start, pause, reset, replay; select scenario type and parameters.
- [ ] Explain in README that this is decision support, not autonomous decision-making.

## Phase 11: Evaluation Harness (build before October, not during)

- [ ] Batch runner: execute 20–30 randomised runs per scenario type from parameters + seeds.
- [ ] Compute precision, recall, F1, false positive rate, false negative rate, and detection latency (in simulated time, per the Track 0 definition).
- [ ] Export results to CSV/JSON for thesis tables and charts.
- [ ] Generate hypotheses from all three generators over identical bundles, anonymised for blind rubric scoring; primary comparison hosted-vs-template at full N, secondary local-vs-hosted at reduced N (per the Phase 8.5 decision).
- [ ] Produce N generations per bundle per model arm; record grounding catch rate, grounding variance, and retry rate **per arm**.
- [ ] Record actual campaign cost and wall-time per arm — both are write-up material, and the cost figure is what makes the "deliberate spend" claim in `thesis_notes.md` concrete.
- [ ] Late-project extensibility demonstration: add a third source adapter and record files touched, lines changed, and hours taken (RQ1 evidence).
- [ ] Dry-run the full evaluation once in early October before the real runs.

## Phase 12: Docker, CI, and Polish

- [ ] Extend Docker Compose to run frontend, backend, and database together.
- [ ] Add CI for frontend tests/build and backend tests.
- [ ] Add linting checks.
- [ ] Basic dependency audit only — no further security tooling in v1.

## Review Prompts

- [ ] Can I explain this change back in plain English?
- [ ] Did I add only the files needed for the current behavior?
- [ ] Did I run tests before asking for review?
- [ ] Did the README change if the project behavior or setup changed?
- [ ] What tradeoff did I choose, and what did I postpone?
- [ ] Does this change serve an evaluation result or a research question — or is it just a feature?
