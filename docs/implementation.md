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

## Phase 4: MapView Boundary

- [ ] Install MapLibre GL JS only when the placeholder no longer teaches enough. (MapLibre, not Mapbox — no account or token needed; see `em_fusion_v2.md` section 10.)
- [ ] Pick a free tile source and add `.env.example` with its URL.
- [ ] Create a small `MapView` adapter component — the only file that imports the map library.
- [ ] Show a graceful placeholder if no tile source is configured.
- [ ] Mock `MapView` in React tests.
- [ ] Manually verify the real map in the browser.
- [ ] Record the diff size for the boundary — it is a cheap second data point for the RQ1 substitutability argument (`thesis_notes.md`).

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

## Phase 9: Constrained AI Hypothesis Layer (RQ3 — core deliverable)

- [ ] Define the hypothesis output schema in Pydantic (title, confidence Low/Medium/High only, summary, supporting evidence, uncertainty, alternatives, recommended action).
- [ ] Build the template-based hypothesis generator first — it is both the fallback and the evaluation comparison baseline.
- [ ] Implement the AI call: fixed low temperature, evidence bundle in, JSON out, bounded retry on invalid JSON, fall back to template generator on repeated failure.
- [ ] Implement the automated grounding check: every supporting-evidence item must trace back to the bundle; flag or reject ungrounded hypotheses; log the catch rate (this is a reportable result).
- [ ] Keep confidence as Low, Medium, or High — no fake numerical precision.
- [ ] Test with mocked AI responses: valid output passes, invalid JSON retries then falls back, ungrounded claims are caught.
- [ ] Update README with the constrained-AI design and why it is safer.

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
- [ ] Generate hypothesis pairs (template vs AI) per bundle, anonymised for blind rubric scoring; produce N AI generations per bundle and record grounding variance.
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
