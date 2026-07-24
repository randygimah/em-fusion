# EM Fusion — Academic Scope Extract (for coding context)

This is the subset of `EM-Fusion-Project-Scope-v2.docx` (MSc thesis scope, July 2026) relevant to
implementation decisions. The docx is the authoritative source for academic framing, literature
review, timeline, risks, and thesis structure — this file exists so that context survives without
committing the binary docx. If this file and the docx disagree, the docx wins. For build-facing
technical detail (endpoints, DB schema, tech stack), `em_fusion_v2.md` remains authoritative.

Working title: **EM Fusion: A Human-in-the-Loop AI Prototype for Explainable Electromagnetic
Situational Awareness**.

## Research Questions

**Main RQ:** How can an EM situational awareness prototype use heterogeneous data fusion, anomaly
detection, and AI-assisted inference to support explainable human decision-making in congested and
contested environments?

- **RQ1 — Data Abstraction and Fusion.** How can heterogeneous EM-relevant data sources be
  normalised into a canonical data model through a Data Abstraction Layer? Focus: architecture,
  adapters, validation, provenance, and *empirically demonstrated* extensibility (the third
  late-project adapter exists to measure this — files touched, lines changed, hours taken).
- **RQ2 — Anomaly Detection.** How effectively can baseline comparison and anomaly detection
  identify deviations in synthetic RF and replayed movement telemetry? Focus: measurable detection
  performance across many parameterised scenario runs with known ground truth.
- **RQ3 — AI-Assisted Hypothesis Generation.** How can a constrained AI inference layer generate
  explainable hypotheses while preserving human-in-the-loop judgement and avoiding unsupported
  conclusions? Focus: evidence grounding, output validation, uncertainty, alternative explanations,
  comparison against a template-based baseline.

Every non-trivial build decision should be traceable to one of these three. If a feature doesn't
serve RQ1, RQ2, or RQ3 (or the evaluation harness that measures them), it's probably scope creep —
see "Review Prompts" in `implementation.md`.

## Objectives (build-relevant)

- Modular architecture ingesting heterogeneous open, replayed, and synthetic EM-relevant sources.
- A DAL converting source-specific inputs into a canonical observation model, with validation and
  provenance.
- Geospatial, time-windowed storage and querying via PostgreSQL + PostGIS.
- A parameterised, seeded scenario generator producing repeatable randomised runs.
- Deterministic baseline comparison and anomaly detection (threshold rules, rolling averages,
  z-score deviation, spatial clustering).
- Structured evidence bundles from detected anomalies.
- A constrained AI inference layer converting evidence bundles into schema-validated,
  evidence-grounded hypotheses, plus a template-based generator as comparison baseline.
- A React geospatial dashboard for inspecting observations, anomalies, hypotheses, and capturing
  analyst verdicts.
- An evaluation harness running scenarios in batch and computing detection metrics and grounding
  statistics.

## Architecture Rationale

A **modular monolith** (single FastAPI app with clear internal module boundaries: `api`,
`adapters`, `dal`, `models`, `schemas`, `services` — `baseline`, `anomaly_detection`, `evidence`,
`hypothesis`, `scenario` — and `repositories`) is preferred over microservices: easier to build in
the timeline, easier to test and evaluate, easier to explain in the thesis, and can evolve into
separate services later if required. This is the reasoning behind the `backend/app/` layout implied
by `em_fusion_v2.md`.

Pipeline: source adapters → DAL → canonical observations → validation + provenance → PostgreSQL/
PostGIS → baseline engine → anomaly detection → evidence bundle builder → constrained AI inference
→ FastAPI API → React dashboard → analyst feedback (persisted back to the store).

## Constrained AI Hypothesis Layer — detail behind `em_fusion_v2.md` section 5.5

- **Input**: the AI receives only a structured JSON evidence bundle (anomaly type, time window,
  affected area, data mode, evidence list with source/finding/rule ID, known uncertainties). It
  never inspects raw unfiltered data.
- **Output**: hypothesis title, confidence (Low/Medium/High only), summary, supporting evidence,
  evidence against/uncertainty, alternative explanations, recommended human action.
- **Validation**: Pydantic schema validation; invalid JSON → bounded retry → fall back to the
  template generator.
- **Grounding check**: every supporting-evidence string is programmatically checked for
  traceability back to the evidence bundle; ungrounded hypotheses are flagged/rejected; the catch
  rate is itself a reportable RQ3 result, not just a safety net.
- **Non-determinism handling**: fixed low temperature; for evaluation, N generations per bundle are
  produced and grounding/quality variance across them is reported.
- The specific hosted LLM/API will be named in the proposal; prompt, schema, and validation code
  should live in the repo for reproducibility.

## Canonical Data Model (entities behind the DB design in `em_fusion_v2.md` section 9)

- `Observation` — observation_id, source_id, source_type, observation_type, timestamp, location,
  confidence, data_mode, validation_status, provenance, payload.
- `TrackObservation` (payload specialisation) — aircraft_id, callsign, altitude, velocity, heading,
  update_gap, continuity_score.
- `RFObservation` (payload specialisation) — sensor_id, frequency_mhz, band, power_dbm, snr_db,
  bandwidth_khz, signal_type, baseline_delta, severity.
- `SourceHealthObservation` (payload specialisation, late-adapter) — source_id, latency,
  availability, error_count, freshness_status.
- `AnomalyEvent` — anomaly_id, anomaly_type, severity, affected_area, time_window, score,
  evidence_refs.
- `Hypothesis` — hypothesis_id, title, confidence, status, affected_area, time_window,
  supporting_evidence, uncertainty, alternatives.
- `AnalystFeedback` — feedback_id, hypothesis_id, verdict, note, timestamp.

PostGIS is justified by one concrete spatial query: clustering track discontinuities within a fixed
radius (e.g. 20km) of an RF anomaly zone.

## Scenario Types (drive the scenario generator and evaluation harness)

Five types, each run as a batch of 20–30 randomised runs per type from parameters + seed, with known
ground truth: (1) normal baseline, (2) GNSS degradation / possible interference, (3) RF sensor fault
(single-sensor), (4) aircraft data-source coverage gap, (5) ambiguous mixed evidence. **Scenarios 3
and 4 are deliberately negative/discriminating cases** — correctly *not* claiming interference is a
first-class evaluation result, not a non-event.

## Evaluation Strategy (what the evaluation harness must actually produce)

- **Anomaly detection**: precision, recall, F1, false positive rate, false negative rate, detection
  latency — latency defined in *simulated scenario time* (injected event onset → anomaly emission),
  never wall-clock, fixed before any measurement code exists.
- **Hypothesis quality**: 1–5 rubric (correctness, evidence grounding, clarity, alternative
  explanations, uncertainty handling, consistency with stated confidence, usefulness, absence of
  unsupported claims), scored **blind** (scorer doesn't know template vs AI), comparing the two
  generators. The automated grounding check catch-rate is the objective complement to this rubric.
- **User evaluation**: 3–6 technical participants, within-subject (raw tables vs EM Fusion
  dashboard), measuring task completion time, accuracy, confidence, NASA-TLX workload, perceived
  usefulness. Requires university ethics approval (4–8 week lead time — see Track 0 in
  `implementation.md`) and written employer clearance (participation, screenshots, repo visibility).

## Success Criteria (build must ultimately demonstrate)

- Heterogeneous data normalised through the DAL; third-source extensibility demonstrated with
  measured effort.
- RF and telemetry fused by time/location via PostGIS spatial queries.
- Baseline comparison detects meaningful deviations; precision/recall/F1 reported across batches.
- The system distinguishes scenario types, including correctly avoiding interference overclaims on
  sensor-fault/coverage-gap runs.
- AI hypotheses are grounded, verified by the automated check, with a reported catch rate.
- Analyst verdicts change hypothesis status through the UI.
- Evaluation gives measurable detection performance and hypothesis quality, with bias controls and
  stated limitations.

## Explicitly Future Work (Discussion chapter only — never build commitments)

Multi-agent hypothesis generation, TimescaleDB, additional context sources (weather/space
weather/maritime), real-time push infrastructure, ML anomaly detectors, real-data integration
pathways. See also `em_fusion_v2.md` section 15 and `em_fusion.md` section 19/20 for the longer v2+
list.
