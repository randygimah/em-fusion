# EM Fusion V1 Implementation Checklist

Use this as a learning checklist, not a rigid sprint plan. For each step, try the implementation first, keep changes small, run tests, update the README, then ask for review when you want feedback.

## Working Rules

- [ ] Before coding a step, write down the user-visible behavior you are trying to create.
- [ ] Write or update a test before polishing the UI.
- [ ] Prefer analyst-visible tests over implementation details like CSS class names.
- [ ] Keep mock data shaped like the future API response.
- [ ] Update `README.md` or the relevant package README whenever setup, scripts, scope, or behavior changes.
- [ ] After each step, ask: what would happen if we did the simpler or more general version instead?

## Phase 1: Frontend Foundation

- [x] Create the Vite React TypeScript app in `frontend/em_fusion`.
- [x] Install Tailwind, Vitest, and Testing Library.
- [x] Wire Tailwind into Vite.
- [x] Add `npm test` and `npm run test:watch`.
- [x] Add Testing Library setup for Vitest.
- [x] Replace the starter smoke test with an analyst-visible test.
- [x] Build the smallest operational-picture UI that passes the first test.
- [x] Remove remaining unused starter assets when you are comfortable using a deletion command.

## Phase 2: Contract-First Mock Data

- [x] Identify the operational-picture fields the UI needs for lesson one.
- [x] Extract the current inline scenario data into a small mock data module.
- [x] Define TypeScript types for the operational-picture contract.
- [ ] Update the test to prove the UI renders from the mock contract.
- [ ] Add one extra assertion only if it represents analyst value.
- [ ] Update README with the contract-first mock data approach.

## Phase 3: Operational Picture Layout

- [ ] Add a left navigation shell with only the v1 sections needed now.
- [ ] Improve the top status bar using the design tokens from `DESIGN.md`.
- [ ] Create a map placeholder component with aircraft, RF sensor, and anomaly-zone labels.
- [ ] Keep Mapbox behind a future `MapView` boundary rather than spreading map logic through the app.
- [ ] Add a timeline strip with two or three scenario events.
- [ ] Test the main analyst story, not the exact layout mechanics.

## Phase 4: Mapbox Boundary

- [ ] Install Mapbox GL JS only when the placeholder no longer teaches enough.
- [ ] Add `.env.example` with `VITE_MAPBOX_TOKEN`.
- [ ] Create a small `MapView` adapter component.
- [ ] Show a graceful placeholder if the token is missing.
- [ ] Mock `MapView` in React tests.
- [ ] Manually verify the real map in the browser.

## Phase 5: FastAPI Contract Mirror

- [ ] Create the smallest FastAPI app with `/health`.
- [ ] Add a backend test for `/health`.
- [ ] Add `/operational-picture` returning the same shape as the frontend mock data.
- [ ] Add a backend contract test for the response shape.
- [ ] Connect the frontend to the endpoint behind a small API function.
- [ ] Keep the mock fallback until backend integration is stable.

## Phase 6: Scenario and Hypothesis Logic

- [ ] Move GNSS degradation data into a scenario fixture.
- [ ] Add a normal environment fixture for comparison.
- [ ] Add a simple rule that explains why the GNSS hypothesis exists.
- [ ] Test the rule with both degraded and normal scenarios.
- [ ] Keep confidence as Low, Medium, or High rather than fake precision.
- [ ] Update README with the current scenario story.

## Phase 7: Human Feedback

- [ ] Add analyst actions: confirm, reject, needs more evidence.
- [ ] Add a note field only after the action flow works.
- [ ] Store feedback in backend memory or a simple persistence layer first.
- [ ] Test that submitting feedback changes hypothesis status.
- [ ] Explain in README that this is decision support, not autonomous decision-making.

## Phase 8: Docker and CI

- [ ] Add Docker only after frontend and backend can run separately.
- [ ] Add Docker Compose for frontend, backend, and database.
- [ ] Add CI for frontend tests/build and backend tests.
- [ ] Add linting checks.
- [ ] Add security scanning as a final v1 polish step.

## Review Prompts

- [ ] Can I explain this change back in plain English?
- [ ] Did I add only the files needed for the current behavior?
- [ ] Did I run tests before asking for review?
- [ ] Did the README change if the project behavior or setup changed?
- [ ] What tradeoff did I choose, and what did I postpone?
