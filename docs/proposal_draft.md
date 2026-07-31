# DTS Proposal and TOR — Working Draft

Draft for `DTS Proposal and TOR project template v4.docx`. The template itself is left untouched;
paste from here once a section is agreed.

**Specialism:** Software Engineering
**Sources:** `em_fusion_v2.md` (technical scope), `research_scope.md` / `EM-Fusion-Project-Scope-v2.docx`
(academic framing), `implementation.md` (build phases), `thesis_notes.md` (decision rationale),
`qa.md` (plain-language concept explanations), `EPA Supplementary Table.pdf` (KSBs).

**Language rule for this document:** written to be understood by an employer representative and an
EPA assessor, not only by a software engineer. Technical terms are introduced in plain words first.

## Status

| Section | Words | Status |
|---|---|---|
| **Part 1 — Proposal** (summary boxes) | ~650 total | **Drafted** |
| **TOR 1. Background to project** | ~500 | **Drafted** |
| **TOR 2. Proposed work** | ~500 | **Drafted** |
| **TOR 3. Aims** | ~150 | **Drafted** |
| **TOR 4. Objectives** | ~150 | **Drafted** |
| **TOR 5. Skills** | ~200 | **Drafted** |
| **TOR 6. Knowledge and behaviours** | ~150 | **Drafted** |
| **TOR 7. Resources** | ~200 | **Drafted** |
| **TOR 8. Unmet business need** | ~200 | **Drafted** |
| **TOR 9. Ethics, social, legal, professional** | ~300 | **Drafted** |
| **TOR 10. Project plan / Gantt** | ~150 | **Drafted — capacity is tight, see the note** |
| **References (Harvard)** | — | **Drafted — three need verification** |
| **Appendix — KSB checkboxes** | — | **Drafted, with two flagged as weak** |

**Word limits:** treated as ±10%. Going over is acceptable; the author trims.

---

# Part 1 — Proposal

*Identity fields (student name, student ID, course, HEI supervisor) to be completed by the author.*

## Project title

**EM Fusion: A Human-in-the-Loop AI Prototype for Explainable Electromagnetic Situational Awareness**

## Define the problem within the business (100 words)

Analysts working in the electromagnetic environment reason across several dissimilar data feeds at
once: platform telemetry, sensor observations, radio noise patterns, and the health of the feeds
themselves. When something changes, they must judge quickly whether they are seeing deliberate
interference, an equipment fault, a problem with the data feed, or nothing meaningful at all. Those
explanations look very similar in any single feed, so separating them means correlating several by
time and location — largely by hand, under time pressure. No existing tooling both fuses these feeds
and explains what their combination implies.

*(96 words)*

## Alignment of project to an identified (i) business challenge and (ii) research opportunity (100 words)

**(i) Business challenge.** My employer has identified improving electromagnetic situational
awareness as a capability initiative: reducing manual data-processing burden, surfacing anomalies
faster, and helping analysts reason about causes. A production capability is a large undertaking, and
the architectural and assurance questions beneath it can be answered cheaply at prototype scale
first.

**(ii) Research opportunity.** The obvious remedy — pointing a large language model at the data — is
the wrong shape of solution, because a system that can invent evidence is unusable where a false
claim is costly. The opportunity is to test whether a *constrained* AI layer, permitted to discuss
only evidence a deterministic pipeline has already established, is both trustworthy and useful.

*(109 words)*

## Present your solution (150 words)

EM Fusion is a prototype decision-support application. It ingests two dissimilar sources — real
aircraft movement data replayed from a public archive, and synthetic radio-sensor readings generated
under scenario control — and converts both into a single common observation format through a Data
Abstraction Layer that validates every record, quarantines malformed ones, and records where each
came from.

Stored observations are compared against baseline behaviour by deterministic rules only: thresholds,
rolling averages, z-scores, and geographic clustering. Related deviations are grouped into an
evidence bundle, and only that bundle — never raw data — reaches the AI layer, which returns a
structured hypothesis: title, a Low/Medium/High confidence level, supporting evidence, stated
uncertainty, alternative explanations, and a recommended action.

Every hypothesis is schema-validated and automatically checked so that each claim traces back to the
bundle. A human analyst then confirms, rejects, or challenges it through a three-screen dashboard.
This is decision support; the analyst's judgement is final.

*(158 words)*

## Define deliverables and success criteria (100 words)

**Deliverables:** a working prototype comprising the Data Abstraction Layer, deterministic detection
engine, constrained AI hypothesis layer, and three-screen analyst dashboard; a reproducible
evaluation harness; and a 10,000-word thesis.

**Success is measured, not demonstrated.** The system detects injected anomalies across twenty to
thirty randomised runs for each of five scenario types, with precision, recall, F1, and
false-positive and false-negative rates reported — and stays quiet on normal runs. Adding a third
data source is completed with effort recorded. Every AI hypothesis passes schema validation, with the
grounding check's catch rate reported. Analyst verdicts change hypothesis status end to end.

*(104 words)*

## State your plan or approach (50 words)

An incremental, evaluation-led build in small phases, each tested against analyst-visible behaviour
under version control with automated testing. Deterministic detection is built and proven before any
AI is introduced, and the template hypothesis generator is built before the AI generator, so the
latter has a baseline to be measured against.

*(52 words)*

## Broadly outline your project schedule

| Period | Focus |
|---|---|
| **August** | Proposal, ethics application, employer clearance; OpenSky data acquisition; map boundary and API contract |
| **September** | Database persistence, scenario generator, source adapters, Data Abstraction Layer |
| **October** | Detection engine, evidence bundles, constrained AI hypothesis layer; **writing begins** |
| **November** | Evaluation harness, third adapter, evaluation campaign, user study; writing continues |
| **December** | Final writing, supervisor feedback, revision, submission |

Approximately 254 hours across twenty-one weeks. The ethics application starts immediately: approval
takes four to eight weeks and gates the user study.

## Conclusions (50 words)

EM Fusion tests whether constrained AI can turn fused, heterogeneous observations into explainable
hypotheses an analyst can trust. It delivers measured evidence rather than a demonstration —
detection performance, extensibility effort, and grounding reliability — answering cheaply the
questions a production capability would otherwise have to answer expensively.

*(48 words)*

---

# Part 2 — Terms of Reference (TOR)

## TOR 1. Background to project (approx. 500 words)

> *Template guidance: describe the context and answer "why this project?", from both your own
> perspective as an apprentice and the employer's. Make clear the application area and the knowledge
> and skills involved. Briefly state the nature of the product or the research question, and the
> problem domain.*

Modern defence organisations depend increasingly on their ability to collect, combine, interpret and
act on data quickly. The electromagnetic environment — the radio spectrum that navigation,
communications and sensing all rely on — is a particularly demanding case. It is *congested*, because
more systems compete for the same frequencies every year, and *contested*, because that spectrum can
be degraded deliberately as well as accidentally.

An analyst working in that environment does not watch a single screen. They reason across several at
once: platform telemetry, sensor observations, radio noise patterns, the health of the data feeds
themselves, environmental conditions, and a sense of what normal looked like historically. When
something changes — a navigation signal weakens, aircraft positions stop updating, one sensor begins
reporting oddly — the analyst has to judge quickly whether they are seeing interference, an equipment
fault, a problem with the data feed, or nothing meaningful at all. Those explanations look very
similar in any one feed. Separating them means correlating several feeds by time and location,
largely by hand, under time pressure.

Two strategic drivers make this worth addressing now. The UK Strategic Defence Review 2025 describes
a changing threat environment and the need for modernised capability, including investment in cyber
and electromagnetic capabilities. The UK Defence Artificial Intelligence Strategy sets a parallel
expectation: that defence adopts AI at pace and scale while remaining effective, efficient, trusted
and responsible. The tension between those two is exactly where this project sits. Speed argues for
automation; trust argues for restraint — particularly where an automated system might assert that
interference is occurring when it is not.

My employer has an identified initiative to improve situational awareness in this area: reducing the
manual data-processing burden on analysts, surfacing anomalies faster, and helping analysts reason
through the possible causes of signal degradation, data-source disruption, or unusual platform
behaviour. A production capability of that kind is substantially larger than anything deliverable
within a master's project. This project is therefore deliberately scoped as a small prototype — on
the order of five per cent of a production system — intended to test the architectural and
AI-assurance questions cheaply, using only open, replayed and synthetic data, before those same
questions have to be answered expensively at full scale.

From my own perspective as an apprentice on the Software Engineering specialism, the project is
attractive precisely because it is not a single-discipline exercise. It requires system architecture,
data engineering, backend and frontend development, database design, AI integration, automated
testing, and continuous integration — and, unusually for a build project, a genuine empirical
evaluation rather than a demonstration.

The product is EM Fusion: a prototype that ingests replayed public aircraft telemetry and synthetic
radio-sensor readings, normalises both into one common data format, detects deviations from baseline
behaviour using deterministic rules, and passes the resulting evidence to a constrained AI layer that
produces written, evidence-backed hypotheses for a human analyst to accept, reject, or challenge. The
practical software engineering question it addresses is:

> *How can heterogeneous data, anomaly detection, and constrained AI inference be combined into an
> explainable decision-support system for electromagnetic situational awareness?*

Throughout, this is decision support rather than decision-making. Every hypothesis ends at a human
verdict.

*(534 words)*

---

## TOR 2. Proposed work: alignment with an identified (i) business challenge and (ii) research opportunity (approx. 500 words)

> *Template guidance: give more detail on what you propose to do — the work involved and your
> approach, covering both technical aspects and general processes; the questions you will address;
> enough detail about the product to define scope; and what technologies you will use and why. After
> reading this section the reader should know what undertaking the project would involve.*

The **business challenge** is the one described above: analysts correlating several data feeds by
hand, under time pressure, to separate interference from equipment faults from problems with the data
itself. The **research opportunity** is that the obvious remedy — pointing a large language model at
the data and asking what is happening — is the wrong shape of solution, because a system that can
invent evidence is unusable where the cost of a false claim is high. The opportunity is to establish
whether a *constrained* AI layer, permitted to discuss only evidence that a deterministic pipeline
has already established, can be both trustworthy enough to accept and useful enough to be worth
having.

EM Fusion is a single web application built as a modular monolith — one deployable system with
clearly separated internal parts — chosen over microservices because it is faster to build, easier to
test, and easier to explain. Data flows through it in one direction. Source adapters convert each
incoming feed into a common format. A Data Abstraction Layer validates every record, quarantines
malformed ones rather than silently discarding them, and attaches provenance recording where each
record came from. Observations are stored in a spatial database. A baseline engine establishes what
normal looks like, deterministic rules detect deviations from it, related deviations are grouped into
an evidence bundle, and only that bundle — never raw data — reaches the AI layer.

Three questions are addressed. First, how dissimilar sources can be normalised into one common model,
measured by adding a third data source late in the project and recording the effort required. Second,
how effectively deterministic detection identifies deviations, measured across twenty to thirty
randomised runs for each of five scenario types with known correct answers. Third, how a constrained
AI layer can produce explainable hypotheses without unsupported conclusions, measured by an automated
grounding check that traces every claim back to the evidence bundle and reports how often it catches
one that does not trace.

The approach is incremental and evaluation-led. Work proceeds in small phases, each with tests
written against analyst-visible behaviour rather than internal implementation detail, under version
control with automated testing and linting on every change. The evaluation harness is treated as a
first-class deliverable built in early October rather than as an afterthought, because the
contribution rests on measured results rather than on feature count.

Technology choices favour maturity and low cost. Python and FastAPI for the backend, where the data
and AI ecosystem is strongest. PostgreSQL with the PostGIS extension for storage, chosen specifically
because one detection rule — clustering aircraft track discontinuities within a set distance of a
radio anomaly — requires indexed geographic queries that a general-purpose database cannot perform
efficiently. React and TypeScript for the dashboard, with MapLibre GL JS for mapping because it needs
no commercial account. For hypothesis generation, a hosted frontier language model accessed by API is
the primary generator, with a locally-run open-weight model serving both as a fallback when the API
is unavailable and as a second arm in the evaluation. Docker Compose runs the whole system locally.

Scope is bounded deliberately: no real radio hardware, no classified data, no claims about detecting
real-world jamming, no machine-learning detectors, and no autonomous decisions. These exclusions
protect both the safety framing and the time reserved for evaluation.

*(543 words)*

---

## TOR 3. Aims (approx. 150 words)

> *Template guidance: an overall statement of what the project is intended to accomplish, expressed
> in terms relating to the project rather than personal achievements. Normally one or two aims.*

The aim of this project is to design, build, and evaluate a working prototype, EM Fusion, that helps
a human analyst make sense of unusual behaviour in the electromagnetic environment.

The prototype brings together two very different kinds of information: real aircraft movement data
replayed from a public archive, and simulated radio-sensor readings. It converts both into a single
common format, compares them against normal behaviour to identify deviations, and then uses a
tightly constrained AI layer to turn those deviations into written explanations. Every explanation
is supported by traceable evidence, carries a plain confidence level, and is presented for a human
analyst to accept, reject, or challenge.

A second aim, equally weighted, is to evaluate the prototype rather than merely demonstrate it:
to measure how reliably it detects what it should, how well it avoids claiming more than the
evidence supports, and whether its explanations are genuinely useful to an analyst.

*(149 words)*

---

## TOR 4. Objectives (approx. 150 words)

> *Template guidance: each objective should identify an expected outcome, and it should be obvious
> by the end whether it was accomplished. SMART.*

1. **Data abstraction.** Deliver a layer that normalises two dissimilar sources into one observation
   format with validation, quarantine of malformed records, and provenance — evidenced by adding a
   third source late in the project and recording files touched, lines changed, and hours taken.
2. **Repeatable scenarios.** Deliver a generator in which every run is exactly reproducible from its
   type, parameters, and random seed.
3. **Detection.** Implement deterministic detection only, and report precision, recall, F1, and
   false-positive and false-negative rates across 20–30 randomised runs for each of five scenario
   types.
4. **Constrained AI.** Produce schema-valid, evidence-grounded hypotheses, and report the proportion
   of ungrounded claims caught by an automated grounding check.
5. **Human-in-the-loop interface.** Deliver three screens in which an analyst's verdict changes a
   hypothesis's recorded status.
6. **Evaluation.** Blind-score hypothesis quality against a template baseline, and run an
   ethics-approved study with 3–6 participants measuring task time, accuracy, and perceived workload.

*(178 words — trimmable to ~150 by cutting the parenthetical detail in objective 1 if the limit is
enforced strictly.)*

---

## TOR 5. Skills (approx. 200 words)

> *Template guidance: identify and list the skills needed. Say how any acquired during the project
> will be acquired. Explicitly identify both familiar areas and new or enhanced ones.*

**Familiar skills.** Day-to-day engineering practice supplies most of the build: architecting and
implementing an application with good automated test coverage; driving technology decisions and
making reasoned recommendations between competing options; backend and frontend development; source
control, code review, containerisation, and continuous integration; and accountability for the
quality of what is delivered — source code, tests, design, and documentation.

**New or enhanced skills.** Four areas extend beyond current practice.

*Geospatial querying* — designing indexed spatial queries in PostGIS — is new. It will be acquired
from the official documentation and a small throwaway proof-of-concept written before the real schema
is committed.

*Constrained AI integration* — schema-enforced generation and automated grounding checks — is new. It
will be developed by building the deterministic template generator first, so that the AI layer has a
working comparison to be measured against rather than being assessed on its own terms.

*Empirical evaluation design* — defining ground truth, selecting metrics, and controlling for bias
through blind scoring — is a research skill rather than an engineering one, and will be developed
with supervisor guidance.

*Stakeholder negotiation* will be exercised in obtaining written employer clearance, securing
university ethics approval, and recruiting study participants — engagements with defined outcomes
rather than informal conversations.

*(213 words)*

---

## TOR 6. Knowledge and behaviours (approx. 150 words)

> *Template guidance: identify and list the knowledge and behaviours needed, distinguishing familiar
> from new or enhanced, and saying how new ones will be acquired.*

**Familiar knowledge.** The rationale for developing a software solution within an organisational
context; the requirements, constraints and security considerations that shape an architecture;
approaches to modularising an application's internal structure; and how to design and deploy software
that meets stakeholder requirements securely.

**New or enhanced knowledge.** Three areas are new. The *electromagnetic domain* itself — how
analysts reason about signal degradation, sensor faults and data-source gaps — is being acquired
through structured reading and discussion with colleagues, and recorded as it is learned.
*Responsible-AI assurance*, including principles set out in the UK Defence AI Strategy and the NIST
AI Risk Management Framework, informs the constrained-AI design directly. Third, the *range of
metrics used to evaluate a delivered software product* is developed in depth through the evaluation
harness.

**Behaviours.** The project is self-directed and largely solo, requiring originality in problem
solving and autonomous planning against a fixed deadline. Most behavioural criteria are assessed
through the professional discussion rather than the project report; this project supplies the
evidence that discussion draws on.

*(168 words)*

---

## TOR 7. Resources — hardware and software required (approx. 200 words)

> *Template guidance: ensure all resources needed are in fact available. A bulleted list is
> sufficient. Consider carefully how you would cope if a resource were unavailable, and what
> alternatives might be used — particularly important where you intend to use your own equipment or
> that of an external body.*

**Hardware** — personal laptop (Apple M4 Pro, 48 GB unified memory), already owned; sufficient memory
to run a local open-weight model alongside the full application stack. *If unavailable:* everything
except the local model runs on any 16 GB machine via Docker Compose and Git, and the local model is
itself a fallback component, so its loss degrades the evaluation's second arm rather than the
prototype.

**Software** — all open-source and free of licence cost: Python and FastAPI, PostgreSQL with PostGIS,
React and TypeScript, Docker Desktop, MapLibre GL JS, Ollama, Git and GitHub Actions. No procurement
dependency.

**Data** — OpenSky Network historical state vectors: free, downloaded once as a static archive,
subject to attribution. *If unavailable:* the archive is taken early and version-controlled with a
checksum manifest, removing any ongoing external dependency.

**Hosted AI API** — approximately £20–30 for the full evaluation campaign, self-funded, with a spend
cap configured in advance. *If unavailable or over budget:* the locally-run model and the
deterministic template generator are already built as fallbacks.

**People** — 3–6 colleagues for the user study, subject to written employer clearance; university
supervisor; university ethics committee. *If unavailable:* the evaluation has three independent
strands, so the thesis remains defensible on detection metrics and blind-scored hypothesis quality
should the user study shrink or be lost.

*(228 words)*

---

## TOR 8. How the project aligns with an unmet business need, including fit (approx. 200 words)

> *Template guidance: relate the project to a real and unmet need for the business or employer. Work
> should be discussed with line manager and/or colleagues to ensure the project has real value.*

The unmet need is practical and current. Analysts working across electromagnetic data have no tooling
that both *fuses* several dissimilar feeds and *explains* what their combination implies. Existing
tools present feeds side by side; correlating them by time and location, and judging whether a change
indicates interference, an equipment fault, or a data problem, remains manual work under time
pressure. My employer has identified improving this as a capability initiative, and the scope of this
project has been discussed and agreed with my line manager.

A production capability of that kind is a large undertaking. Before committing to one, three
questions need answering — and all three can be answered cheaply at prototype scale using open and
synthetic data:

1. Can a canonical abstraction layer make new data sources genuinely cheap to add? This project
   *measures* that — files touched, lines changed, hours taken — rather than asserting it.
2. Does deterministic detection perform well enough against known ground truth to be worth building
   on, and does it stay quiet when nothing is wrong?
3. Can an AI layer be constrained tightly enough to be trusted where a false claim is expensive?

The deliverable to the business is therefore not the prototype itself but the evidence it produces:
a reference architecture, measured detection performance, and a quantified answer on whether
constrained AI hypothesis generation is safe and useful enough to pursue at scale.

*(232 words)*

---

## TOR 9. Ethics, Social, Legal and Professional Issues (approx. 300 words)

> *Template guidance: consider any ethics, social, legal and professional issues that might arise.
> Refer to university guidance on Ethics and Integrity.*

**Ethics.** The user evaluation involves human participants and requires university ethics approval,
which will be submitted alongside this proposal — approval can take four to eight weeks, and a late
application risks losing the study entirely. Participants will be colleagues, which introduces a
power dynamic that must be managed rather than ignored: participation will be genuinely voluntary,
recruitment will avoid anyone in a line-management relationship with me, no record will be kept of
who declines, and participants may withdraw without giving a reason. Only task times, accuracy and
workload ratings are collected, and results are reported anonymised.

**Social.** The project sits in a defence context and is deliberately bounded: it uses only open,
replayed and synthetic data, makes no claim to detect real interference, and performs no emitter
identification, geolocation or targeting. The most significant social risk is automation bias — an
analyst over-trusting a plausible-sounding machine explanation. The design mitigates this directly by
always presenting uncertainty and alternative explanations, expressing confidence categorically
rather than as a false-precision percentage, and requiring a human verdict before any hypothesis is
resolved.

**Legal.** Aviation telemetry is public transponder data used under the OpenSky Network's licence
with attribution recorded; it concerns aircraft rather than individuals, and no attempt is made to
link it to owners. No classified or employer-proprietary data is used at any point, and evidence
bundles sent to the hosted AI API contain only synthetic and open data. Repository visibility, and
any pre-submission review requirement, will be confirmed with my employer in writing early in the
project.

**Professional.** Work follows the BCS Code of Conduct, particularly competence and acting in the
public interest. Results will be reported honestly, including negative ones — a finding that the AI
layer does not outperform the template baseline is a legitimate result and will be reported as such.
Prompts, schemas and validation code are included in the repository so results can be independently
checked.

*(327 words)*

---

## TOR 10. Project Plan — schedule of activities (approx. 150 words)

> *Template guidance: a Gantt chart expressed in weeks. Identify the tasks needed to achieve each
> objective, estimate how long they will take, plan when they should be done. Clearly indicate for
> each task the number of hours' work required and the elapsed time over which it should be done.*

The project runs from August to the end of December, approximately twenty-one weeks. Available effort
is 5–10 hours per week initially, rising to 10–15 hours per week from September, giving a planned
budget of roughly 240 hours against an estimated requirement of 254.

Three scheduling decisions follow. First, the non-code track — ethics application and employer
clearance — starts immediately, because ethics approval takes four to eight weeks and gates the user
study. Second, writing begins in October alongside the final build phases rather than after them; the
draft is not left until the build is finished. Third, December is treated as working time with
contingency inside it, not as pure buffer.

Phases already complete (frontend foundation and contract-first mock data) are excluded from the
estimate.

*(153 words)*

### Task breakdown

| # | Task | Objective served | Hours | Elapsed |
|---|---|---|---|---|
| 1 | Track 0: proposal, ethics application, employer clearance | All | 10 | 3 wks |
| 2 | OpenSky acquisition: download, bounding-box filter, archive + manifest | 1 | 5 | 1 wk |
| 3 | MapView boundary and map integration | 5 | 8 | 2 wks |
| 4 | FastAPI contract mirror and frontend polling | 5 | 8 | 2 wks |
| 5 | PostgreSQL/PostGIS schema, repositories, spatial query | 1 | 16 | 3 wks |
| 6 | Scenario generator, source adapters, Data Abstraction Layer | 1, 2 | 18 | 3 wks |
| 7 | Baseline engine, deterministic detection, evidence bundles | 3 | 20 | 3 wks |
| 8 | AI prerequisites gate (model pinning, spend caps, smoke test) | 4 | 6 | 1 wk |
| 9 | Constrained AI hypothesis layer, three generators, grounding check | 4 | 20 | 3 wks |
| 10 | Analyst feedback workflow and Scenario Control screen | 5 | 12 | 2 wks |
| 11 | Evaluation harness and third adapter (extensibility measurement) | 1, 6 | 18 | 2 wks |
| 12 | Docker Compose, CI, linting, polish | — | 8 | 1 wk |
| 13 | Evaluation campaign: batch runs, blind scoring, analysis | 3, 4, 6 | 14 | 2 wks |
| 14 | User study: recruitment, sessions, analysis | 6 | 14 | 3 wks |
| 15 | Thesis writing (10,000 words) | All | 65 | 12 wks |
| 16 | Supervisor feedback, revision, final edits | All | 12 | 3 wks |
| | **Total** | | **254** | |

### Gantt (half-month blocks)

| # | Task | Aug<br>1 | Aug<br>2 | Sep<br>1 | Sep<br>2 | Oct<br>1 | Oct<br>2 | Nov<br>1 | Nov<br>2 | Dec<br>1 | Dec<br>2 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Track 0 (ethics, clearance) | ▓ | ▓ | ▓ | | | | | | | |
| 2 | OpenSky acquisition | | ▓ | | | | | | | | |
| 3 | MapView boundary | ▓ | ▓ | | | | | | | | |
| 4 | FastAPI contract mirror | | ▓ | ▓ | | | | | | | |
| 5 | PostGIS persistence | | | ▓ | ▓ | | | | | | |
| 6 | Scenario generator + DAL | | | | ▓ | ▓ | | | | | |
| 7 | Detection + evidence bundles | | | | | ▓ | ▓ | | | | |
| 8 | AI prerequisites gate | | | | | ▓ | | | | | |
| 9 | AI hypothesis layer | | | | | | ▓ | ▓ | | | |
| 10 | Feedback + Scenario Control | | | | | | ▓ | ▓ | | | |
| 11 | Evaluation harness + 3rd adapter | | | | | | | ▓ | ▓ | | |
| 12 | Docker, CI, polish | | | | | | | | ▓ | | |
| 13 | Evaluation campaign | | | | | | | | ▓ | ▓ | |
| 14 | User study | | | | | | ▓ | ▓ | ▓ | | |
| 15 | Thesis writing | | | | | ▓ | ▓ | ▓ | ▓ | ▓ | |
| 16 | Feedback, revision, final edits | | | | | | | | | ▓ | ▓ |

### Capacity note — read before submitting

The estimate of **254 hours** should be compared against three availability cases across the
twenty-one weeks:

| Case | Assumption | Available | Verdict |
|---|---|---|---|
| Low | 5 h/wk throughout Aug–Sep, 10 h/wk Oct–Dec | ~170 h | **Does not fit.** The user study is the strand to drop — the evaluation stays defensible on detection metrics and blind-scored hypothesis quality |
| Planned | 7.5 h/wk Aug, 10 h/wk Sep, 13 h/wk Oct–Dec | ~240 h | **Marginal — 14 hours short.** Workable if writing genuinely starts in October and December is working time |
| High | 10 h/wk Aug–Sep, 15 h/wk Oct–Dec | ~275 h | Fits with ~20 hours of contingency |

The plan assumes the ramp to 10 h/wk happens in **September, not October**. Holding 5 h/wk through
September costs roughly 20 hours at the point in the schedule where the DAL and detection work sits,
and pushes the AI layer into November — which in turn compresses writing.

---

## Appendix — KSB checklist mapping

Which boxes to tick, and where each is evidenced. **Two are weak for this project and should be a
conversation with your supervisor rather than a silent tick.**

### Core KSBs assessed by Project Report (all four in the template's checklist)

| Core KSB (PR) | Tick | Evidenced by |
|---|---|---|
| Identify, document, review and design complex IT-enabled business processes… systematic approach to improving those processes | ✅ | The analyst triage workflow *is* the business process being redesigned: raw feeds → normalised observations → detected anomalies → evidence bundles → reviewed hypotheses → recorded verdict |
| Professionally present specialism plans and solutions in a well-structured business report | ✅ | The thesis itself, plus this TOR |
| Demonstrate self-direction and originality in solving problems; act autonomously | ✅ | Solo project, self-defined scope, documented design decisions and reversals |
| Be competent at negotiating and closing techniques with senior internal and external stakeholders | ✅ | Employer clearance obtained in writing; university ethics approval; participant recruitment — each a negotiation with a defined close |

### Software Engineering specialism — Skills (6)

| # | Skill | Tick | Notes |
|---|---|---|---|
| 1 | Architect, build and support concurrent software platforms, performant, responsive, good test coverage | ✅ | Full-stack build with test coverage throughout |
| 2 | Drive technology decision-making; evaluate design/implementation options; make reasoned proposals incl. DevOps and Cloud | ✅ | **Strongest fit.** The documented decisions — lakehouse rejected, MapLibre over Mapbox, hosted vs local model, polling over WebSockets — are exactly this, with rationale recorded |
| 3 | Develop distributed or semi-complex solutions… innovative user experiences… encompassing cross-functional teams, platforms and technologies | ⚠️ | Semi-complex and multi-platform: yes. **"Cross-functional teams" is weak on a solo project** |
| 4 | Update current software products, improving efficiency and functionality; build new features to product specifications | ⚠️ | **Weakest fit.** This is a greenfield build, not the improvement of an existing product |
| 5 | Accomplish planned development tasks delivering expected features within time, security and quality requirements | ✅ | Phased plan with a fixed December deadline |
| 6 | Be accountable for quality of deliverables (code quality, automated testing, design quality, documentation) and standard processes | ✅ | CI, linting, tests, documented architecture |

### Software Engineering specialism — Knowledge

Note: the KSB table lists **six** knowledge criteria; the template's appendix provides **five**
checkboxes. Worth querying with your supervisor rather than guessing which to drop.

| # | Knowledge | Tick | Notes |
|---|---|---|---|
| 1 | Rationale for software platform and solution development, including organisational context | ✅ | TOR 1 and TOR 8 |
| 2 | Inputs, requirements, security considerations and constraints guiding solution architecture | ✅ | Requirements and NFRs, including the safety boundary |
| 3 | Methodologies for organising the software engineering process, lifecycle activities, and managing delivery risk | ✅ | Phased incremental build; documented risk register |
| 4 | Approaches to modularising the internal structure of an application; structure and behaviour of business applications | ✅ | Modular monolith with explicit internal boundaries; the DAL and MapView adapter are the argument |
| 5 | How to design, develop and deploy secure, effective solutions meeting stakeholder requirements | ✅ | Docker Compose deployment; secrets handling; dependency audit |
| 6 | The range of metrics used to evaluate a delivered software product | ✅ | **Strongest fit.** The entire evaluation harness — precision, recall, F1, FPR/FNR, latency, grounding catch rate |

---

## Open items

1. **Identity fields** — student name, student ID, course title as registered, HEI supervisor.
   *Author to complete.*
2. **Gantt effort** — hours per task are required by the template; figures will be proposed from the
   scope-document timeline and must be sanity-checked against actual availability.
3. **Employer naming** — TOR 1 and TOR 8 currently say "my employer" without naming the organisation
   or the initiative. Check whether either can be named in a document that reaches an external EPA
   assessor, and whether the employer requires sight of the proposal before submission. This is
   already a Track 0 item in `implementation.md`.

## References (Harvard)

⚠️ **Three of these need verification before submission — marked below.** I have written them in
Harvard form from knowledge, not from the published documents, and citation details are exactly the
kind of thing that is easy to get subtly wrong.

BCS, The Chartered Institute for IT (2022) *BCS Code of Conduct*. Swindon: BCS. **⚠️ Verify the
current version and its year — BCS revises this periodically. Also confirm your institution expects
BCS rather than its own integrity policy.**

HM Government (2025) *Strategic Defence Review 2025*. London: HM Government. **⚠️ Verify the exact
title, publishing body, and date. This is the reference I am least confident about — it may be
published under the Ministry of Defence, and the full title may carry a subtitle.**

Ministry of Defence (2022) *Defence Artificial Intelligence Strategy*. London: Ministry of Defence.

National Institute of Standards and Technology (2023) *Artificial Intelligence Risk Management
Framework (AI RMF 1.0)*. NIST AI 100-1. Gaithersburg, MD: NIST.

OpenSky Network (2026) *Historical state vector data*. Available at:
https://opensky-network.org/data/ (Accessed: *[date of download]*). **⚠️ Confirm the exact URL and
the attribution wording their licence requires — this must be recorded at download time, and is
already a Track 0 item.**

Schäfer, M., Strohmeier, M., Lenders, V., Martinovic, I. and Wilhelm, M. (2014) 'Bringing up OpenSky:
a large-scale ADS-B sensor network for research', in *Proceedings of the 13th International Symposium
on Information Processing in Sensor Networks (IPSN)*. IEEE, pp. 83–94. **⚠️ Verify page numbers.**

### Not yet cited but likely needed

The TOR does not require a literature review, so this list is deliberately short. The thesis
literature review (2,000 words across four themes) will need substantially more — data fusion and
abstraction layers, anomaly detection in telemetry, human-in-the-loop and explainable AI decision
support, and defence AI assurance. Worth starting that reading list now rather than in October.
