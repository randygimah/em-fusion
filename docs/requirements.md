# EM Fusion — Requirements (v1 build, scope v2)

The requirements baseline for the v1 build. Every spec item in `spec.jsonl` traces to at least one
requirement here, and every requirement here traces to at least one spec item.

**Authority.** This document restates and numbers requirements; it does not create scope. Technical
content comes from `em_fusion_v2.md`; academic framing comes from `research_scope.md` and the docx.
The structure (user stories, NFR categories, acceptance flow) follows `em_fusion.md`, the superseded
v1 PRD, but its cut features — WebSockets, the RF/IQ ML classifier, Isolation Forest / DBSCAN, and
the eight-screen navigation — are **not** requirements. Where this file and `em_fusion_v2.md`
disagree, `em_fusion_v2.md` wins and this file is wrong and must be corrected.

**Confidence rule, applying to every requirement below.** Confidence and severity are always
`Low | Medium | High`. Never a percentage, never a decimal. This holds in the AI output schema, in
the database, in API responses, and on every screen.

---

## 1. Personas

| Persona | Description | Primary need |
|---|---|---|
| **Analyst** | The human in the loop. Reviews the operational picture and adjudicates hypotheses. Not a developer. | See what is anomalous, understand why the system thinks so, and record a judgement. |
| **Engineer** | Builds and operates the prototype. | Reproducible runs, a stable data contract, a system that can be run end to end locally. |
| **Researcher** | The dissertation author, evaluating the system. | Batch runs with ground truth, exportable metrics, a queryable hosted-vs-template hypothesis comparison. |

---

## 2. User Stories

### Analyst

- **US-A1** — As an analyst, I want the operational picture to show only anomalous items by default,
  so that I am not scanning nominal data under time pressure.
- **US-A2** — As an analyst, I want to see aircraft tracks, RF sensors, and anomaly zones on one map,
  so that I can compare movement anomalies against signal anomalies in the same spatial frame.
- **US-A3** — As an analyst, I want anomalous items highlighted distinctly on the map and selectable,
  so that I can move from "something is wrong there" to the evidence behind it in one click.
- **US-A4** — As an analyst, I want each hypothesis to show its supporting evidence with rule IDs,
  so that I can trace every claim back to a detection rather than trusting a summary.
- **US-A5** — As an analyst, I want uncertainty and alternative explanations shown alongside every
  hypothesis, so that I am not anchored on a single interpretation.
- **US-A6** — As an analyst, I want to confirm, reject, mark as needing more evidence, or mark as a
  false positive, so that human judgement is captured and final.
- **US-A7** — As an analyst, I want to always see whether data is synthetic or replayed, so that I
  never mistake the prototype for an operational feed.
- **US-A8** — As an analyst, I want to see which generator produced a hypothesis, so that a fallback
  is visible to me rather than silently substituted.
- **US-A9** — As an analyst, I want to switch the view between anomalous items only, nominal items
  only, and all items, so that I can compare an anomaly against normal behaviour in the same frame
  rather than inferring the contrast.
- **US-A10** — As an analyst, I want to play back a run's aircraft movement on the map, so that I can
  see how tracks developed and where continuity broke, instead of reading a static snapshot.

### Engineer

- **US-E1** — As an engineer, I want every scenario run reproducible from type + parameters + seed,
  so that any result can be regenerated exactly.
- **US-E2** — As an engineer, I want a single canonical observation model behind a Data Abstraction
  Layer, so that adding a source touches adapters and nothing else.
- **US-E3** — As an engineer, I want malformed records quarantined rather than dropped or fatal, so
  that a bad source degrades the picture instead of stopping ingest.
- **US-E4** — As an engineer, I want the API to expose the fused picture over plain HTTP polling, so
  that no push infrastructure has to be built, operated, or defended.
- **US-E5** — As an engineer, I want the whole system to run under Docker Compose, so that it can be
  demonstrated on one machine with no cloud account.
- **US-E6** — As an engineer, I want CI to run tests and lint on both halves of the stack, so that
  quality checks are part of delivery rather than a pre-submission scramble.
- **US-E7** — As an engineer, I want one command surface at the repo root to build, run, seed, and
  test the whole stack in containers, so that no per-service incantations have to be remembered.

### Researcher

- **US-R1** — As a researcher, I want the AI layer to receive only structured evidence bundles, so
  that hypotheses cannot be based on invented evidence.
- **US-R2** — As a researcher, I want batch runs with exported metrics, so that detection performance
  has statistical weight instead of one data point per scenario.
- **US-R3** — As a researcher, I want template, hosted-AI, and local-AI hypotheses stored with a
  generator flag and model ID, so that the hosted-vs-template blind comparison is queryable and any
  fallback to the local or template generator is visible in the data rather than inferred.
- **US-R4** — As a researcher, I want raw model responses persisted verbatim, so that results stay
  defensible after a hosted model is retired.
- **US-R5** — As a researcher, I want a correct non-detection on a normal-baseline run treated as a
  first-class result, so that the false-positive rate means something.
- **US-R6** — As a researcher, I want the cost of adding a third source adapter measured, so that the
  extensibility claim is evidenced rather than asserted.

---

## 3. Functional Requirements

### FR-1xx — Source Adapters and Data Abstraction Layer

| ID | Requirement |
|---|---|
| FR-101 | The DAL shall normalise every incoming record into a single canonical observation model regardless of source. |
| FR-102 | The DAL shall validate required fields on every record before acceptance. |
| FR-103 | The DAL shall quarantine records failing validation: stored, countable, attributable to a source — never silently dropped, and never fatal to the ingest run. |
| FR-104 | The DAL shall attach provenance (source ID, source type, data mode, scenario run ID) to every accepted record. |
| FR-105 | An aviation adapter shall replay archived OpenSky state vectors from file, with no live API dependency at demo time. |
| FR-106 | An RF adapter shall emit synthetic RF observations under scenario control, carrying channel index, channel centre frequency, band, power, SNR, bandwidth, signal type, sensor ID, sensor location, and baseline delta. |
| FR-107 | A third source adapter shall be addable late in the project, with files touched, lines changed, and hours taken recorded as RQ1 evidence. |
| FR-108 | RF observations shall be emitted on a fixed sensor × channel × time grid: six to eight sensors at recorded positions, each reporting on eight 2 MHz channels centred on 1567.42–1581.42 MHz with one channel centred exactly on GNSS L1 (1575.42 MHz). Every sensor shall report on every channel at every interval, so a missing reading is a detectable gap rather than an ambiguous absence. |
| FR-109 | Sensor positions and the channel plan shall be configuration, not hard-coded constants, and sensors shall be positioned so that a candidate interference zone contains some and excludes others. |
| FR-110 | The bounding-box-filtered OpenSky extract shall be archived as Parquet and committed to the repository with its manifest, so the pipeline reproduces from a fresh clone with no download step. Parquet shall be the archive format for that extract only and shall never serve as a read path for observations, which are served from PostGIS. |

### FR-2xx — Scenario Generator

| ID | Requirement |
|---|---|
| FR-201 | Every scenario run shall be defined by a scenario type, a parameter set, and a random seed, and shall be fully reproducible from those three values alone. |
| FR-202 | The generator shall support five scenario types: normal baseline, GNSS signal degradation, RF sensor fault, aircraft data-source coverage gap, ambiguous mixed evidence. |
| FR-203 | Parameters shall include at minimum noise amplitude, gap duration, number of affected sensors, affected-area size, event timing, and seed. |
| FR-204 | Each run shall record its ground truth (what was injected, where, and when) alongside its parameters. |
| FR-205 | The generator shall support batch execution of 20–30 randomised runs per scenario type. |
| FR-206 | Spectral extent shall be a parameter of the GNSS degradation scenario — narrowband confined to the L1 channel, or broadband across the grid — not a sixth scenario type. |
| FR-207 | Ground truth shall be recorded on the scenario run and read by the evaluation harness only. No adapter, DAL record, detector input, API response, or evidence bundle shall carry it, whether as a field, a label, or an inferable artefact such as a scenario-type string on an observation. |

### FR-3xx — Baseline and Anomaly Detection

| ID | Requirement |
|---|---|
| FR-301 | Detection shall use deterministic methods only: threshold rules, rolling averages, z-score deviation, and PostGIS spatial clustering. No ML detectors in v1. |
| FR-302 | A baseline engine shall compute rolling averages over normal-scenario runs, against which deviations are measured. |
| FR-303 | Rule RF-NOISE: RF power or SNR beyond baseline threshold shall raise an anomaly. |
| FR-304 | Rule TRACK-GAP: aircraft position staleness beyond threshold shall raise a track-continuity anomaly. |
| FR-305 | Rule FUSION-SPATIAL: RF noise anomalies and clustered track gaps in the same time window and area shall raise a possible-interference-zone anomaly. |
| FR-306 | Rule SOURCE-GAP: track dropouts with no co-located RF anomaly shall raise a possible data-source issue. |
| FR-307 | Rule SENSOR-FAULT: one RF sensor abnormal while spatial neighbours are nominal shall raise a possible sensor fault. |
| FR-308 | A normal-baseline run shall raise zero anomalies. Correct non-detection is a required behaviour, not an absence of behaviour. |
| FR-309 | Detection latency shall be measured in simulated scenario time from event onset to anomaly emission, never in wall-clock time. |

### FR-4xx — Evidence Bundles

| ID | Requirement |
|---|---|
| FR-401 | An evidence bundle builder shall group related anomalies into a single structured bundle containing anomaly type, time window, affected area, data mode, evidence items, and known uncertainties. |
| FR-402 | Every evidence item shall carry a source, a finding, and a rule ID. |
| FR-403 | Every evidence item shall trace to a stored anomaly or observation. A bundle containing an untraceable item shall fail to build. |
| FR-404 | The evidence bundle shall be the only input the AI layer receives. Raw observations shall never reach a model. |

### FR-5xx — Constrained AI Hypothesis Layer

| ID | Requirement |
|---|---|
| FR-501 | The hypothesis output schema shall be Pydantic-enforced with fields: hypothesis title, confidence (`Low\|Medium\|High`), summary, supporting evidence, evidence against / uncertainty, alternative explanations, recommended human action. |
| FR-502 | A template generator shall produce a schema-valid hypothesis from a bundle with no model involved. It is both the correctness fallback and the evaluation baseline. |
| FR-503 | All generators shall sit behind one provider-agnostic service interface (`evidence_bundle -> validated hypothesis`), with provider, model ID, and generation parameters supplied by config. |
| FR-504 | A hosted generator shall use the provider's native JSON-schema-constrained output, making structurally invalid output unrepresentable at generation time. |
| FR-505 | A local generator shall enforce the same schema via a compiled grammar. |
| FR-506 | Generation parameters shall be frozen and identical across arms (temperature 0, fixed seed, fixed max tokens). |
| FR-507 | A dated model ID shall be pinned, never a moving alias, and recorded per hypothesis. |
| FR-508 | Every hypothesis shall persist `generator`, `model_id`, `generation_params`, and verbatim `raw_response`. |
| FR-509 | Availability fallback: if the hosted arm is unreachable, generation shall fall through to the local arm without an error state reaching the analyst. |
| FR-510 | Correctness fallback: schema or grounding failure after bounded retry shall fall through to the template generator. Retries shall have an explicit ceiling with no unbounded recursion. |
| FR-511 | The two fallbacks shall be separate code paths and shall be described separately in the write-up. |
| FR-512 | An automated grounding check shall verify that every supporting-evidence item traces back to the bundle. Ungrounded hypotheses shall be flagged or rejected, and the catch rate logged per arm. |
| FR-513 | A run-level call budget shall abort a run when exceeded, independent of any provider-console spend cap. |
| FR-514 | Per-call token and cost logging shall be in place from the first model call. |

### FR-6xx — Human-in-the-Loop Validation

| ID | Requirement |
|---|---|
| FR-601 | An analyst shall be able to submit one of four verdicts on any hypothesis: confirm, reject, needs more evidence, false positive. |
| FR-602 | Submitting a verdict shall change hypothesis status and persist. Statuses: New, Under review, Confirmed, Rejected, Inconclusive. |
| FR-603 | An analyst shall be able to attach a free-text note to a verdict. |
| FR-604 | An invalid verdict value shall be rejected without mutating hypothesis state. |

### FR-7xx — Dashboard (three screens)

| ID | Requirement |
|---|---|
| FR-701 | The left navigation shall have exactly three entries: Operational Picture, Hypotheses, Scenario Control. |
| FR-702 | System health shall be a compact status strip in the navigation footer, not a screen. |
| FR-703 | A data-mode badge shall be visible on every screen, stating that the environment is synthetic or replayed. |
| FR-704 | The Operational Picture shall show a map of aircraft, RF sensors, and anomaly zones behind a `MapView` adapter boundary. |
| FR-705 | The `MapView` adapter shall be the only module importing a map library, and shall render a graceful placeholder when no tile source is configured. |
| FR-706 | Anomalous items shall render visually distinct from nominal items on the map and shall be selectable. |
| FR-707 | The Operational Picture right rail shall show active hypothesis cards and a detection summary. |
| FR-708 | The Operational Picture shall have one tabbed exception panel — RF / Tracks / Events — showing anomalous rows only, with a "+n nominal hidden" footer. |
| FR-709 | Full drill-down tables shall be reachable from panel footers, not from the navigation. |
| FR-710 | A timeline strip shall show scenario events in chronological order. |
| FR-711 | Hypothesis Detail shall show title, status, confidence, affected area, time window, supporting evidence with rule-ID chips and grounded markers, uncertainty, alternatives, a zone map thumbnail, a mini timeline, a note field, and verdict buttons. |
| FR-712 | Hypothesis Detail shall carry the disclaimer "Decision support only — analyst judgement is final." |
| FR-713 | The UI shall show which generator produced each hypothesis. |
| FR-714 | Scenario Control shall provide the scenario library, run configuration (parameters, seed, batch count), run controls (start / pause / reset / replay), run status, and a recent-runs table. |
| FR-715 | No confidence, severity, or score shall be rendered as a percentage or decimal anywhere in the UI. |
| FR-716 | A view filter with three states — Anomalous only, Nominal only, All — shall drive the map and the exception panel together, defaulting to Anomalous only. Drill-down tables (FR-709) remain unfiltered; they are the show-everything view by definition. |
| FR-717 | The Operational Picture shall provide a playback transport over a run's simulated time: play, pause, speed selection, and a scrub bar. The map shall render aircraft positions at the cursor with a trailing path, and anomaly zones shall appear and clear as their windows enter and leave the cursor. |
| FR-718 | Playback shall run on polled data with client-side interpolation between buffered frames. No push transport, and the request rate shall not be coupled to the frame rate. |

### FR-8xx — API

| ID | Requirement |
|---|---|
| FR-801 | `GET /health` shall report service liveness. |
| FR-802 | `GET /operational-picture` shall return a payload matching the frontend `OperationalPicture` contract exactly. |
| FR-803 | `GET /aircraft`, `GET /rf-observations`, `GET /anomalies` shall serve the drill-down views. |
| FR-804 | `GET /hypotheses` and `GET /hypotheses/{id}` shall serve hypothesis lists and detail; an unknown ID shall return 404. |
| FR-805 | `POST /hypotheses/{id}/feedback` shall accept a verdict and optional note. |
| FR-806 | `POST /scenario/start`, `POST /scenario/reset`, and `GET /scenario/runs` shall drive and report scenario execution. |
| FR-807 | The frontend shall obtain all data by polling over HTTP. No WebSocket or push transport shall exist in v1. |
| FR-808 | CORS shall be restricted to known origins. |
| FR-809 | `GET /operational-picture` shall accept a `view` parameter of `anomalous`, `nominal`, or `all`, and filter server-side. Because the payload then omits the excluded rows, the response shall carry the suppressed counts as metadata so FR-708's "+n nominal hidden" footer stays truthful. |
| FR-810 | A time-windowed track query shall return aircraft positions across a span of simulated time, so the frontend can buffer ahead of the playback cursor rather than issue one request per frame. |

### FR-9xx — Persistence

| ID | Requirement |
|---|---|
| FR-901 | PostgreSQL with PostGIS shall hold observations, anomalies, evidence bundles, hypotheses, analyst feedback, and scenario runs. |
| FR-902 | Source-specific fields shall live in a typed observation payload so the canonical table stays stable as sources are added. |
| FR-903 | The `hypotheses` table shall carry `generator` (`template\|local\|hosted`), `model_id`, `generation_params`, and `raw_response` from first creation, not by later migration. |
| FR-904 | A repository layer shall hold all SQL and spatial logic; route handlers shall contain none. |
| FR-905 | At least one real PostGIS spatial query shall exist: track discontinuities within N km of an RF anomaly zone. |
| FR-906 | Schema changes shall follow a documented migration convention. |

### FR-10xx — Evaluation Harness

| ID | Requirement |
|---|---|
| FR-1001 | A batch runner shall execute 20–30 randomised runs per scenario type from parameters and seeds. |
| FR-1002 | The harness shall compute precision, recall, F1, false positive rate, false negative rate, and detection latency in simulated time. |
| FR-1003 | The harness shall export results to CSV and JSON. |
| FR-1004 | The harness shall generate hypotheses from the hosted and template generators over a stratified sample of identical bundles, and export them anonymised, identically formatted, and in randomised within-bundle order for blind rubric scoring, with the arm key held separately. The local generator is not blind-scored. |
| FR-1005 | The harness shall record grounding catch rate, grounding variance, retry rate, campaign cost, and wall-time per arm, over all generations rather than only the scored sample. |
| FR-1006 | The harness shall ingest completed score sheets from two independent raters and report per-dimension means per arm together with quadratic-weighted Cohen's κ across the double-scored corpus. |

### FR-11xx — Build and Delivery

| ID | Requirement |
|---|---|
| FR-1101 | Docker Compose shall run frontend, backend, and database together on one machine. |
| FR-1102 | The local model server shall run on the host and be reached as a Compose config value (`host.docker.internal`), never as a Compose service. |
| FR-1103 | CI shall run backend tests, frontend tests and build, lint on both halves, and a basic dependency audit. |
| FR-1104 | A root `Makefile` shall wrap the Compose stack as the single command surface: `generate` (run a scenario batch), `demo` (generate then bring the stack up), `build`, `test` (backend and frontend suites in containers), `up`, and `down`. `backend/Makefile` is retained for local venv work; the root Makefile is the containerised surface. |

---

## 4. Non-Functional Requirements

### NFR-1xx — Reliability

| ID | Requirement |
|---|---|
| NFR-101 | Replay mode shall be the default. No demo shall depend on a live data API. |
| NFR-102 | The backend shall handle missing or malformed data by quarantining, never by crashing. |
| NFR-103 | The AI layer shall degrade in two steps — hosted unreachable to local, schema/grounding failure to template — without an error state reaching the analyst. |
| NFR-104 | Both fallback paths shall be deliberately exercised and tested, not assumed. |
| NFR-105 | The whole system shall demonstrate offline: no network, no API key, no third-party account. |

### NFR-2xx — Explainability

| ID | Requirement |
|---|---|
| NFR-201 | Every hypothesis shall include supporting evidence, uncertainty, and alternative explanations. |
| NFR-202 | Every supporting-evidence item shall be machine-traceable to its bundle. |
| NFR-203 | Confidence levels shall be categorical, and the meaning of each level shall be documented. |
| NFR-204 | Degradation shall be visible: the producing generator is shown, never hidden. |

### NFR-3xx — Safety

| ID | Requirement |
|---|---|
| NFR-301 | The system shall not provide operational jamming or interference instructions. |
| NFR-302 | The system shall make no claim to detect real hostile emitters. |
| NFR-303 | Every screen and the README shall present the system as a decision-support prototype running on synthetic and replayed data. |
| NFR-304 | Analyst judgement shall be final. No hypothesis shall be auto-actioned. |

### NFR-4xx — Security (proportionate to a prototype)

| ID | Requirement |
|---|---|
| NFR-401 | Secrets shall live in environment variables and never be committed, including in fixtures. |
| NFR-402 | All incoming data shall be validated at the DAL boundary. |
| NFR-403 | CORS shall be restricted. |
| NFR-404 | A basic dependency audit shall run in CI. No further security tooling in v1. |

### NFR-5xx — Performance

| ID | Requirement |
|---|---|
| NFR-501 | The system shall handle hundreds to low thousands of observations per run. |
| NFR-502 | Exception-filtered panels shall keep the default render small; the map shall not render every nominal marker at once. |
| NFR-503 | The polling interval shall be tuned by hand, not prematurely optimised. |

### NFR-6xx — Reproducibility (research-specific)

| ID | Requirement |
|---|---|
| NFR-601 | Every evaluation result shall be regenerable from scenario type + parameters + seed for the deterministic pipeline. |
| NFR-602 | Hosted-arm results shall remain defensible after model retirement through persisted `model_id`, `generation_params`, and `raw_response`. |
| NFR-603 | The local arm shall remain fully regenerable indefinitely. |
| NFR-604 | No detector, API response, or analyst-visible surface shall have access to a run's injected ground truth while that run is scorable. A detector able to see the answer invalidates every metric computed from the run. |

---

## 5. Out of Scope for v1

Anything here goes to `em_fusion_v2.md` section 15 (Future Work) — never quietly back into scope.

```
Real RF hardware integration            RF/IQ dataset ML classifier
Real-time operational EW use            Isolation Forest / DBSCAN / deep learning detectors
Operational jamming detection claims    Multi-agent AI architecture
Hostile emitter identification          WebSockets / real-time push
Emitter geolocation                     TimescaleDB
Adversary targeting                     Additional context sources (weather, space weather, AIS)
Autonomous operational decisions        Knowledge graph
Classified data                         Bayesian hypothesis updating
Production / cloud deployment           Kubernetes / Terraform
Role-based access control               Data lakehouse substrate (Iceberg / Trino / object storage)
Audit logging                           Security scanning beyond a basic dependency audit
```

Screens beyond the three named in FR-701 are out of scope. Drill-down tables are views over the same
API, not screens, and are reached from panels (FR-709).

---

## 6. Acceptance Criteria

The v1 build is accepted when this flow demonstrably works end to end, unassisted.

| ID | Criterion | Traces to |
|---|---|---|
| AC-01 | An analyst starts a seeded scenario from Scenario Control and the run appears in the recent-runs table. | FR-201, FR-714, FR-806 |
| AC-02 | Replayed aircraft and synthetic RF data flow through the DAL into PostGIS, with malformed records quarantined and provenance attached to every accepted record. | FR-101–FR-106, FR-901 |
| AC-03 | The anomaly engine detects the injected deviation on a degraded run. | FR-301–FR-307 |
| AC-04 | The anomaly engine stays quiet on a normal-baseline run. | FR-308 |
| AC-05 | An evidence bundle is built in which every item traces to a stored anomaly or observation. | FR-401–FR-403 |
| AC-06 | The AI layer generates a hypothesis that passes schema validation and the grounding check, or the template fallback fires and is recorded and displayed as such. | FR-501–FR-512, FR-713 |
| AC-07 | With the network off and no API key, the full pipeline still produces hypotheses via the local arm. | NFR-103, NFR-105 |
| AC-08 | The analyst sees anomalous items highlighted on the map, switches the view to All to compare them against nominal traffic, opens the hypothesis, and reads traced evidence, uncertainty, and alternatives. | FR-704–FR-708, FR-711, FR-716, FR-809 |
| AC-08b | The analyst plays back the run's aircraft movement on the map, scrubs to the anomaly window, and sees where track continuity broke. | FR-717, FR-718, FR-810 |
| AC-09 | The analyst submits a verdict, hypothesis status changes, and the decision is persisted and survives a reload. | FR-601–FR-604 |
| AC-10 | The evaluation harness replays 20–30 runs per scenario type and exports precision, recall, F1, FPR, FNR, latency, and grounding statistics. | FR-1001–FR-1005 |
| AC-11 | No percentage or decimal confidence, severity, or score appears anywhere in the UI. | FR-715, NFR-203 |
| AC-12 | The whole system runs via Docker Compose from `make demo` on a clean machine, and CI runs tests and lint on both halves. | FR-1101–FR-1104 |

AC-04 and AC-10 are what turn a demo into a thesis. Neither is optional.

---

## 7. Traceability

`spec.jsonl` is the executable form of this document. Each spec item cites the requirement IDs it
implements; each requirement above should be reachable from at least one spec item. When a
requirement changes, update this file first, then the affected spec items, then the tests, then the
code — in that order. See `../CLAUDE.md` for the spec-driven workflow.
