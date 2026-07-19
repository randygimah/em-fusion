# Project Scope: EM Fusion (v2)

This is the build-facing scope. The academic framing, research questions, evaluation design, and thesis structure live in `EM-Fusion-Project-Scope-v2.docx`. The step-by-step build order lives in `implementation.md`. If the three documents disagree, the docx wins on academic scope and this document wins on technical detail.

## 1. Project Name

**EM Fusion: A Human-in-the-Loop AI Prototype for Explainable Electromagnetic Situational Awareness**

## 2. One-line Summary

EM Fusion is a prototype decision-support platform that fuses replayed open aviation telemetry and synthetic RF sensor observations through a Data Abstraction Layer, detects deviations from baseline behaviour, and converts structured evidence bundles into explainable, machine-validated hypotheses for human analyst review on a geospatial dashboard.

## 3. Core Project Pitch

In congested and contested environments, operators may need to understand whether unusual behaviour in aircraft, positioning systems, or data feeds could indicate interference, degradation, sensor faults, or data-source failure.

This prototype does **not** attempt to build a real military electromagnetic warfare system. It demonstrates how a modern data platform could ingest multiple evidence streams, normalise them into a canonical model, fuse them in time and space, detect anomalies deterministically, and hand a *constrained* AI layer structured evidence from which to generate explainable hypotheses for human review.

The core pattern, and the thing the whole build serves:

```
Data → Validation → Baseline comparison → Anomaly detection
     → Evidence bundle → Constrained AI hypothesis → Automated validation
     → Human review
```

The AI never sees raw unfiltered data and never invents evidence. Its output is schema-validated and grounding-checked before an analyst sees it.

---

## 4. MVP Objective

> Can we build a full-stack prototype that fuses replayed aviation telemetry with synthetic RF observations through a canonical Data Abstraction Layer, detects deviations deterministically, and generates evidence-grounded, machine-validated hypotheses that a human analyst can inspect, challenge, and validate?

The MVP is **decision support**, not autonomous decision-making. Every hypothesis ends at an analyst verdict.

---

## 5. MVP Scope

### Data Sources (v1)

Two sources at launch, a third added late as a measured extensibility demonstration:

1. **Replayed open aviation telemetry** — OpenSky Network historical state vectors, downloaded once, archived, and replayed deterministically from file. No live API dependency: replays are reproducible, offline, and immune to rate limits. Record licence/attribution requirements.
2. **Synthetic RF sensor observations** — generated under scenario control (frequency, band, power, SNR, bandwidth, baseline delta, severity).
3. **Third adapter (late-project)** — a simple additional source (e.g. synthetic source-health feed) added near the end purely to measure DAL extension effort: files touched, lines changed, hours taken. This is RQ1 evidence, not a feature.

Aviation data provides: location, altitude, velocity, track, update gaps, dropout behaviour, continuity scores.

Synthetic RF data provides: frequency band, signal power, SNR, bandwidth, signal type, sensor location, baseline delta, observation time.

**Removed from v1:** the public RF/IQ classification dataset and ML signal classifier. It was a separate ML workflow bolted onto the side of the thesis argument. It moves to future work.

### Core MVP Components

#### 1. Source Adapters and Data Abstraction Layer

Adapters convert source-specific data into internal records and attach source metadata. The DAL then:

- Normalises everything into the canonical observation model
- Validates required fields
- Quarantines malformed records (they are stored and countable, not silently dropped)
- Attaches provenance to every record

This is one of the strongest parts of the project: it is the extensible-architecture claim made real.

#### 2. Parameterised Scenario Generator

The most important MVP component, because it is also the evaluation engine. Every scenario run is defined by a type, a parameter set, and a random seed — and is fully reproducible from those three things.

Scenario types:

```
1. Normal baseline
2. GNSS signal degradation / possible interference
3. RF sensor fault (single-sensor abnormality)
4. Aircraft data-source coverage gap
5. Ambiguous mixed evidence
```

Parameters include: noise amplitude, gap duration, number of affected sensors, affected-area size, event timing, seed.

Example generated scenario:

```
Between 12:10 and 12:25 (simulated):
- RF sensors around Sector A detect increased noise near GNSS L1
- Aircraft update frequency drops within a 20 km area
- Several aircraft tracks become discontinuous
- Expected hypothesis: possible localised GNSS interference, Medium confidence
```

Each scenario type must support batch execution of 20–30 randomised runs with known ground truth. This gives the evaluation statistical weight instead of one data point per scenario.

#### 3. Baseline and Anomaly Detection Engine

Deterministic methods only:

```
Threshold rules
Rolling averages
Z-score deviation
Spatial clustering (PostGIS)
```

Example rules:

```
IF RF noise rises above baseline threshold
AND aircraft update gaps increase in the same area and window
THEN anomaly: possible interference zone

IF aircraft dropouts occur AND no RF anomaly is present
THEN anomaly: possible data-source issue

IF one RF sensor reports abnormal readings AND nearby sensors are normal
THEN anomaly: possible sensor fault
```

**Removed from v1:** Isolation Forest, DBSCAN, change-point detection. Deterministic methods are sufficient for the research questions, easier to explain, and easier to evaluate. ML detectors are future work.

Detection latency is measured in **simulated scenario time** (event onset → anomaly emission), never wall clock. Fix this definition before writing measurement code.

#### 4. Evidence Bundle Builder

Groups related anomalies and prepares the only input the AI layer is allowed to see:

```json
{
  "anomaly_type": "track_continuity_deviation",
  "time_window": "12:10-12:25 UTC",
  "affected_area": "Sector A",
  "data_mode": "Synthetic RF + Open Data Replay",
  "evidence": [
    {"source": "Aircraft replay feed", "finding": "Update rate dropped 62%", "rule_id": "TRACK-GAP-001"},
    {"source": "RF sensors SNS-01, SNS-03", "finding": "Elevated noise near GNSS L1", "rule_id": "RF-NOISE-002"},
    {"source": "Fusion engine", "finding": "Discontinuities clustered within 20km of RF zone", "rule_id": "FUSION-SPATIAL-003"}
  ],
  "known_uncertainties": ["Only synthetic RF data", "Replay feed may contain gaps"]
}
```

Every evidence item must trace to a stored anomaly or observation.

#### 5. Constrained AI Hypothesis Layer

Two generators, same output schema:

- **Template-based generator** — built first. It is both the fallback and the evaluation comparison baseline.
- **AI generator** — a hosted LLM called with the evidence bundle, fixed low temperature, JSON-only output.

Output schema (Pydantic-enforced):

```
hypothesis_title
confidence            (Low | Medium | High — never percentages)
summary
supporting_evidence   (each item must trace to the bundle)
evidence_against_or_uncertainty
alternative_explanations
recommended_human_action
```

Validation pipeline:

1. Schema validation; invalid JSON → bounded retry → fall back to template generator.
2. **Automated grounding check**: every supporting-evidence string must trace back to the evidence bundle. Ungrounded hypotheses are flagged or rejected, and the catch rate is logged — it is a reportable evaluation result, not just a safety net.

Confidence is always Low/Medium/High. Never `Confidence: 87%` — unfounded precision, and it contradicts the thesis argument. The same rule applies to every score shown in the UI: no decimal "signal integrity" or percentage "anomaly score" badges unless backed by a real, documented computation.

#### 6. Human-in-the-Loop Validation

Analyst actions on any hypothesis:

```
Confirm
Reject
Needs more evidence
Mark as false positive
Add analyst note
```

Submitting a verdict changes hypothesis status and is persisted. Hypothesis statuses: New, Under review, Confirmed, Rejected, Inconclusive.

#### 7. Geospatial Dashboard — Three Screens

Left nav has exactly three entries. System health is a compact status strip in the nav footer, not a screen. Confidence and severity render as Low/Med/High labels or pips throughout.

**Screen 1 — Operational Picture**
- Map (behind a `MapView` adapter boundary): aircraft, RF sensors, anomaly zones; "SYNTHETIC ENVIRONMENT DATA" badge
- Right rail: active hypotheses cards + detection summary (Low/Med/High)
- Bottom: a single **tabbed exception panel** — `RF (n anomalous)` / `Tracks (n degraded)` / `Events` — showing only anomalous rows, with "+n nominal hidden · View all →" footers
- "View all →" opens full drill-down tables (full RF observation stream, full track inventory). Drill-downs are reached from panels, not from the nav — they are cheap views over the same API, not screens

**Screen 2 — Hypothesis Detail / Analyst Workbench**
- Title, status, confidence pips, affected area, time window
- Supporting evidence (with rule-ID chips and "grounded ✓" markers), evidence against / uncertainty, alternative explanations
- Zone map thumbnail, mini timeline, analyst note + verdict buttons
- Disclaimer: "Decision support only — analyst judgement is final."

**Screen 3 — Scenario Control**
- Scenario library (the five types), run configuration (parameters + seed + batch count), run controls (start / pause / reset / replay), run status, recent-runs table

This screen is the visible face of the evaluation harness — parameter and seed controls belong here deliberately.

#### 8. API Layer

FastAPI, modular monolith. Example endpoints:

```
GET  /health
GET  /operational-picture
GET  /aircraft
GET  /rf-observations
GET  /anomalies
GET  /hypotheses
GET  /hypotheses/{id}
POST /hypotheses/{id}/feedback
POST /scenario/start
POST /scenario/reset
GET  /scenario/runs
```

**No WebSockets in v1.** The frontend polls. A replay-based prototype does not need push infrastructure, and polling is one sentence to defend in the thesis. WebSockets are future work.

#### 9. Evaluation Harness

A first-class deliverable, not an afterthought:

- Batch runner: 20–30 randomised runs per scenario type from parameters + seeds
- Computes precision, recall, F1, false positive rate, false negative rate, detection latency (simulated time)
- Exports CSV/JSON for thesis tables and charts
- Generates anonymised template-vs-AI hypothesis pairs for blind rubric scoring; produces N AI generations per bundle and records grounding variance
- Dry-run the full evaluation once in early October before the real runs

---

## 6. Out of Scope for v1

```
Real RF hardware integration
Real-time operational EW use
Operational jamming detection claims
Hostile emitter identification / geolocation
Adversary targeting
Autonomous operational decisions
Classified data
Production deployment
RF/IQ dataset ML classifier
Isolation Forest / DBSCAN / deep learning detectors
Multi-agent AI architecture
WebSockets / real-time push
TimescaleDB
Additional context sources (weather, space weather, maritime, AIS)
Knowledge graph
Bayesian hypothesis updating
Kubernetes / Terraform / cloud deployment
Role-based access control, audit logging
Security scanning beyond a basic dependency audit
```

Anything cut from v1 goes into Section 15 (Future Work) or `FUTURE.md` — never quietly back into scope.

---

## 7. High-Level Architecture

```mermaid
flowchart LR
    A[OpenSky Replay File] --> B[Aviation Adapter]
    C[Synthetic RF Generator] --> D[RF Adapter]
    E[Third Source - late extensibility demo] --> F[Adapter 3]

    B --> G[Data Abstraction Layer]
    D --> G
    F --> G

    G --> H[Canonical Observation Model]
    H --> I[Validation + Quarantine + Provenance]
    I --> J[(PostgreSQL + PostGIS)]

    J --> K[Baseline Engine]
    K --> L[Anomaly Detection Engine]
    L --> M[Evidence Bundle Builder]

    M --> N[Constrained AI Hypothesis Layer]
    M --> O[Template Hypothesis Generator]
    N --> P[Schema Validation + Grounding Check]
    O --> P

    P --> Q[FastAPI Backend]
    Q --> R[React Dashboard - 3 screens, polling]
    R --> S[Analyst Verdict]
    S --> J

    J --> T[Evaluation Harness]
    T --> U[Metrics Export CSV/JSON]
```

## 8. Data Flow

```mermaid
sequenceDiagram
    participant Gen as Scenario Generator
    participant DAL as Adapters + DAL
    participant DB as PostgreSQL/PostGIS
    participant Engine as Baseline + Anomaly Engine
    participant Bundle as Evidence Builder
    participant AI as AI Layer (validated)
    participant API as FastAPI
    participant UI as React Dashboard
    participant Analyst as Analyst

    Gen->>DAL: Replayed + synthetic records (seeded run)
    DAL->>DB: Canonical observations + provenance (quarantine invalid)
    Engine->>DB: Read window, compare to baseline
    Engine->>DB: Store anomaly events
    Bundle->>DB: Group anomalies, build evidence bundle
    Bundle->>AI: Structured bundle only
    AI->>AI: Generate → schema-validate → grounding-check
    AI->>DB: Store hypothesis (or template fallback)
    UI->>API: Poll operational picture / hypotheses
    API->>UI: Fused data
    Analyst->>UI: Confirm / reject / needs more evidence / false positive
    UI->>API: Verdict + note
    API->>DB: Persist feedback, update status
```

---

## 9. Database Design

PostgreSQL + PostGIS. PostGIS is justified by real spatial queries in the pipeline — in particular clustering track discontinuities within N km of an RF anomaly zone.

```mermaid
erDiagram
    OBSERVATIONS {
        int id
        string source_id
        string source_type
        string observation_type
        datetime timestamp
        geometry location
        string data_mode
        string validation_status
        json provenance
        json payload
    }
    ANOMALIES {
        int id
        string anomaly_type
        string severity
        datetime start_time
        datetime end_time
        geometry affected_area
        json evidence_refs
    }
    EVIDENCE_BUNDLES {
        int id
        string anomaly_type
        json evidence
        json known_uncertainties
        datetime created_at
    }
    HYPOTHESES {
        int id
        int bundle_id
        string generator
        string title
        string confidence
        string status
        json supporting_evidence
        json uncertainty
        json alternatives
        bool grounding_passed
    }
    ANALYST_FEEDBACK {
        int id
        int hypothesis_id
        string verdict
        string note
        datetime created_at
    }
    SCENARIO_RUNS {
        int id
        string scenario_type
        json parameters
        int seed
        datetime started_at
        json ground_truth
    }

    EVIDENCE_BUNDLES ||--o{ HYPOTHESES : produces
    HYPOTHESES ||--o{ ANALYST_FEEDBACK : receives
    SCENARIO_RUNS ||--o{ OBSERVATIONS : generates
    ANOMALIES }o--|| EVIDENCE_BUNDLES : grouped_into
```

Track/RF/source-health specialisations live in the observation `payload` (typed via Pydantic), keeping the canonical table stable as sources are added. `hypotheses.generator` ("template" | "ai") and `grounding_passed` exist so the evaluation harness can query comparisons directly.

---

## 10. Tech Stack

**Frontend:** React, TypeScript, Vite, Tailwind, Vitest + Testing Library, Zustand (if needed), Mapbox GL JS behind a `MapView` adapter (graceful placeholder when `VITE_MAPBOX_TOKEN` is missing), Recharts.

**Backend:** Python, FastAPI, Pydantic, SQLAlchemy, Uvicorn, Pytest. No Celery, no APScheduler complexity — a simple loop or on-demand replay is enough.

**Data:** PostgreSQL + PostGIS.

**AI:** One hosted LLM API (named in the proposal), called from a single service module. Pandas/NumPy for the evaluation harness.

**DevOps:** Docker, Docker Compose, GitHub Actions (backend tests, frontend tests/build, lint), Ruff, Black, ESLint. Basic dependency audit only.

**Deployment:** Local Docker Compose. That is the v1 target. Cloud is future work.

---

## 11. User Stories

**Analyst**

```
As an analyst, I want the operational picture to show only anomalous items by default so that I am not scanning nominal data under time pressure.
As an analyst, I want each hypothesis to show its supporting evidence with rule IDs so that I can trace every claim to a detection.
As an analyst, I want to see uncertainty and alternative explanations alongside every hypothesis so that I am not anchored on a single interpretation.
As an analyst, I want to confirm, reject, or mark a hypothesis as needing more evidence so that human judgement is captured and final.
```

**Engineer / Researcher**

```
As an engineer, I want every scenario run reproducible from type + parameters + seed so that evaluation results can be regenerated exactly.
As an engineer, I want the AI layer to receive only structured evidence bundles so that hypotheses cannot be based on invented evidence.
As a researcher, I want batch runs with exported metrics so that detection performance has statistical weight.
As a researcher, I want template and AI hypotheses stored with a generator flag so that blind comparison is queryable.
```

---

## 12. Non-Functional Requirements

**Reliability:** replay mode is the default (no live-API dependency in demos); the backend handles missing/malformed data by quarantining, not crashing; the UI always shows the data mode (synthetic/replayed).

**Explainability:** every hypothesis includes supporting evidence, uncertainty, and alternatives; every supporting-evidence item is machine-traceable to the bundle; confidence levels are categorical and their meaning documented.

**Safety:** no operational jamming instructions; no claims about real hostile emitters; every screen and the README present the system as a decision-support prototype on synthetic/replayed data; analyst judgement is final.

**Security (proportionate to a prototype):** secrets in environment variables, never committed; incoming data validated; CORS restricted; basic dependency audit in CI.

**Performance:** hundreds to low thousands of observations per run; exception-filtered panels keep the default render small; polling interval tuned by hand, not prematurely optimised.

---

## 13. Milestone Plan

Aligned with `implementation.md` phases. Track 0 (non-code) runs in parallel from day one: ethics application, employer clearance in writing, OpenSky download + licence notes, latency definition, participant recruitment.

```
M1  Frontend foundation + contract-first mock data          [done]
M2  Three-screen shell, exception panel, MapView boundary
M3  FastAPI contract mirror (polling, mock parity)
M4  PostgreSQL/PostGIS schema, repositories, spatial query
M5  Scenario generator (parameterised, seeded) + adapters + DAL
M6  Baseline + anomaly detection + evidence bundles
M7  Hypothesis layer: template generator → AI generator →
    schema validation → grounding check
M8  Analyst feedback + Scenario Control screen
M9  Evaluation harness (batch runs, metrics, export) +
    third-adapter extensibility demo
M10 Docker Compose (full stack) + CI + lint
```

Success gate for the timeline: the harness dry-run happens in early October, leaving October for real evaluation and writing.

---

## 14. v1 Success Criteria

The MVP is successful if this flow demonstrably works:

```
1. Start a seeded scenario from Scenario Control.
2. Replayed aircraft and synthetic RF data flow through the DAL into PostGIS,
   with malformed records quarantined and provenance attached.
3. The anomaly engine detects the injected deviation (and stays quiet on
   normal-baseline runs).
4. An evidence bundle is built; the AI layer generates a hypothesis that
   passes schema validation and the grounding check (or the template
   fallback fires and is recorded as such).
5. The analyst opens the hypothesis, sees traced evidence, uncertainty, and
   alternatives, and submits a verdict that changes its status.
6. The evaluation harness replays 20–30 runs per scenario type and exports
   precision/recall/F1/FPR/FNR/latency plus grounding statistics.
7. The whole system runs via Docker Compose; CI runs tests and lint.
```

Criterion 3's "stays quiet" and criterion 6's batch export are what turn a demo into a thesis.

---

## 15. Future Work (v2+ — mentioned in the thesis Discussion, never promised)

```
Multi-agent hypothesis generation (retriever / explanation / context / judge)
  compared against the single constrained agent
Bayesian hypothesis updating over categorical confidence
Knowledge graph of sensors, sectors, events, and feedback
ML anomaly detectors (Isolation Forest, change-point detection)
RF/IQ dataset signal classification (CNN on spectrograms / IQ samples)
LLM analyst copilot (retrieval-grounded Q&A over system data)
Additional fusion sources: AIS, weather, space weather, NOTAM-style notices
Passive SDR spectrum ingestion (RTL-SDR / HackRF, receive-only)
WebSocket live feed
TimescaleDB time-series optimisation
Cloud deployment (ECS Fargate, Terraform), RBAC, audit logging
Confidence calibration and analyst agreement-rate tracking
```

---

## 16. Scope Statement

> EM Fusion is a full-stack prototype for AI-assisted electromagnetic situational awareness. It fuses replayed open aviation telemetry with synthetic RF sensor observations through a canonical Data Abstraction Layer, detects deviations from baseline behaviour using deterministic methods, and converts structured evidence bundles into explainable hypotheses via a constrained, schema-validated, grounding-checked AI layer. A human analyst inspects, challenges, and validates every hypothesis through a three-screen geospatial dashboard. The prototype uses only open, replayed, and synthetic data, is evaluated through batch scenario runs with known ground truth, blind-scored hypothesis quality comparison, and a small ethics-approved user study, and is explicitly non-operational decision support.
