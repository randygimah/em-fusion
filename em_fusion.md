# Project Scope: EM Fusion
 

## 1\. Project Name
 
**EM Fusion: AI-Assisted Electromagnetic Situational Awareness Prototype**
 

## 2\. One-line Summary
 
EM Fusion is a prototype decision-support platform that fuses open-source movement telemetry, synthetic RF sensor observations, and AI-assisted anomaly detection to help users identify possible electromagnetic disruption scenarios through an explainable geospatial dashboard.
 

## 3\. Core Project Pitch
 
In congested and contested environments, operators may need to understand whether unusual behaviour in aircraft, vessels, communications, or positioning systems could indicate interference, spoofing, degradation, or data-source failure.
 
This prototype does **not** attempt to build a real military electromagnetic warfare system. Instead, it demonstrates how a modern data platform could ingest multiple evidence streams, fuse them in time and space, detect anomalies, and generate explainable hypotheses for human review.
 
The project is valuable because it combines:
 

    Open data ingestion
    Synthetic RF observation generation
    Geospatial visualisation
    Time-series data storage
    AI-assisted anomaly detection
    Human-in-the-loop hypothesis validation
    API-based information dissemination
    Containerisation, CI/CD, and deployment
    

---
 

# 4\. MVP Objective
 
The MVP should prove the following:
 
> Can we build a full-stack prototype that fuses open aviation telemetry with synthetic RF observations, detects suspicious spatiotemporal patterns, and presents explainable hypotheses to a human analyst?
 
The MVP should focus on **decision support**, not autonomous decision-making.
 
---
 

# 5\. MVP Scope
 

## Included in Version 1
 

### Data Sources
 
Version 1 should include three main data streams:
 

    1. Open aviation telemetry
    2. Synthetic RF sensor observations
    3. Public RF/IQ classification dataset for AI demonstration
    

The key point is that aviation data and RF data should be treated differently.
 
Aviation data gives us:
 

    Aircraft location
    Altitude
    Velocity
    Track
    Update gaps
    Possible dropout behaviour
    

Synthetic RF data gives you:
 

    Frequency band
    Signal power
    Signal-to-noise ratio
    Bandwidth
    Signal type
    Sensor location
    Time of observation
    

Public RF/IQ datasets can be used to demonstrate:
 

    Signal pattern classification
    Modulation classification
    ML workflow
    Model inference integration
    

---
 

## Core MVP Features
 

### 1\. Data Ingestion
 
The backend should ingest or generate:
 

    Aircraft track data
    Synthetic RF observations
    Scenario events
    Anomaly events
    Hypothesis records
    

The first version can use a mixture of:
 

    Live API ingestion
    Stored replay data
    Synthetic scenario generator
    

A replay mode is useful because it makes the demo more reliable. Live APIs can fail, rate-limit, or produce boring data.
 
---
 

### 2\. Synthetic Scenario Generator
 
This is one of the most important MVP components.
 
You should create a Python script that can simulate several scenarios:
 

    Normal environment
    Congested RF environment
    Possible GNSS interference
    Aircraft data dropout
    Sensor outage
    False positive / API coverage gap
    

Example synthetic scenario:
 

    Between 12:10 and 12:25:
    - RF sensors around Sector A detect increased noise around GNSS L1 frequency.
    - Aircraft update frequency drops within a 20 km area.
    - Several aircraft tracks become discontinuous.
    - The system generates a hypothesis: Possible localised GNSS interference.
    

This gives you control over demo.
 
---
 

### 3\. Fusion Engine
 
The fusion engine should align data by:
 

    Time
    Location
    Source
    Event type
    Confidence
    

It should answer questions like:
 

    Did aircraft data dropouts and RF noise spikes happen in the same area?
    Did they happen during the same time window?
    Are multiple independent sources supporting the same hypothesis?
    Is there an alternative explanation?
    

This can start as rule-based logic.
 
---
 

### 4\. Anomaly Detection Engine
 
Version 1 should include two levels of detection.
 

### Rule-based Detection
 
Example rules:
 

    IF RF noise rises above normal threshold
    AND aircraft update gaps increase in the same area
    THEN create anomaly: possible interference zone
    

    IF aircraft dropouts occur
    AND no RF anomaly is present
    THEN create anomaly: possible data-source issue
    

    IF one RF sensor reports abnormal readings
    AND nearby sensors remain normal
    THEN create anomaly: possible sensor fault
    

### Simple ML-based Detection
 
Use one simple method first:
 

    Isolation Forest
    DBSCAN clustering
    Rolling z-score
    Change-point detection
    

For MVP, we do not need a complex deep learning model. A clear, explainable anomaly detector is better.
 
---
 

### 5\. Hypothesis Engine
 
The hypothesis engine should convert anomalies into analyst-friendly explanations.
 
Example hypothesis:
 

    Hypothesis:
    Possible localised GNSS interference in Sector A
    
    Confidence:
    Medium
    
    Evidence:
    - Aircraft update rate dropped by 62% between 12:10 and 12:25.
    - Synthetic RF sensors SNS-01 and SNS-03 detected elevated noise near GNSS L1.
    - Affected aircraft tracks show discontinuity within the same geospatial area.
    
    Alternative explanations:
    - API data coverage gap
    - Sensor outage
    - Weather or space-weather related degradation
    - Normal traffic density variation
    
    Recommended analyst action:
    Review evidence and confirm, reject, or mark as inconclusive.
    

Avoid using fake precision such as:
 

    Confidence: 87%
    

Use:
 

    Low
    Medium
    High
    

This is more realistic unless we have properly calibrated probabilities.
 
---
 

### 6\. Human-in-the-Loop Validation
 
The UI should allow the user to review system-generated hypotheses and respond with:
 

    Confirm
    Reject
    Needs more evidence
    Mark as false positive
    Add analyst note
    

This is important because it shows that the AI is supporting human reasoning, not replacing it.
 
---
 

### 7\. Geospatial Dashboard
 
The frontend should include:
 

    Map view
    Timeline view
    RF observation panel
    Aircraft track panel
    Anomaly list
    Hypothesis detail panel
    Evidence trail
    

The map should show:
 

    Aircraft positions
    Synthetic RF sensor locations
    Anomaly zones
    Contested/degraded areas
    Hypothesis markers
    

---
 

### 8\. API Layer
 
The system should expose data through FastAPI endpoints.
 
Example endpoints:
 

    GET /health
    GET /aircraft
    GET /rf-observations
    GET /anomalies
    GET /hypotheses
    GET /hypotheses/{id}
    POST /hypotheses/{id}/feedback
    POST /scenario/start
    POST /scenario/reset
    

Optional WebSocket endpoint:
 

    /ws/live-feed
    

This can push live events to the frontend.
 
---
 

# 6\. Out of Scope for MVP
 
To keep the project realistic, these should be excluded from Version 1:
 

    Real RF hardware integration
    Real-time tactical military decision-making
    Emitter geolocation from real sensors
    Operational jamming detection claims
    Autonomous recommendations
    Classified data
    Knowledge graph
    Bayesian network
    Multi-agent AI architecture
    Complex deep learning pipeline
    Full cloud-native Kubernetes deployment
    

We can mention these as future work, but do not put them in the first build.
 
---
 

# 7\. High-Level Architecture
 

    flowchart LR
        A[Open Aviation API / Replay Data] --> B[Python Ingestion Worker]
        C[Synthetic RF Scenario Generator] --> B
        D[ RF/IQ Dataset Classifier] --> E[AI Inference Service]
    
        B --> F[(PostgreSQL + PostGIS / TimescaleDB)]
        E --> F
    
        F --> G[FastAPI Backend]
        G --> H[React Dashboard]
        G --> I[External API Consumers]
    
        G --> J[WebSocket Live Feed]
        J --> H
    
        K[Human Analyst Feedback] --> H
        H --> G
        G --> F
    

---
 

# 8\. Data Flow Architecture
 

    sequenceDiagram
        participant Source as Data Source
        participant Worker as Ingestion Worker
        participant DB as Database
        participant Engine as Fusion & Anomaly Engine
        participant API as FastAPI Backend
        participant UI as React Dashboard
        participant Analyst as Human Analyst
    
        Source->>Worker: Aircraft / RF / Scenario data
        Worker->>DB: Store raw observations
        Engine->>DB: Read recent observations
        Engine->>Engine: Align by time and location
        Engine->>Engine: Detect anomalies
        Engine->>DB: Store anomaly and hypothesis
        UI->>API: Request latest operational picture
        API->>DB: Fetch tracks, RF observations, anomalies
        API->>UI: Return fused data
        UI->>Analyst: Display map, evidence, hypotheses
        Analyst->>UI: Confirm / reject / add note
        UI->>API: Submit feedback
        API->>DB: Store analyst validation
    

---
 

# 9\. System Components
 

## Component 1: Data Ingestion Worker
 
Responsible for:
 

    Fetching aircraft telemetry
    Loading replay data
    Generating synthetic RF observations
    Normalising timestamps
    Validating incoming data
    Writing observations to the database
    

Suggested tools:
 

    Python
    Requests / HTTPX
    Pydantic
    SQLAlchemy
    APScheduler or simple loop
    

For MVP, avoid overengineering with Celery unless we really need distributed tasks.
 
---
 

## Component 2: Scenario Generator
 
Responsible for creating controlled demo scenarios.
 
Example scenarios:
 

    normal_environment.json
    gnss_interference_sector_a.json
    sensor_failure_sns_02.json
    aircraft_dropout_cluster.json
    false_positive_api_gap.json
    

Each scenario should define:
 

    Start time
    End time
    Affected area
    RF sensor behaviour
    Aircraft track behaviour
    Expected anomaly
    Expected hypothesis
    

This makes the project testable.
 
---
 

## Component 3: Database Layer
 
Recommended database:
 

    PostgreSQL + PostGIS
    

Optional extension:
 

    TimescaleDB
    

Use PostgreSQL first. Add TimescaleDB if we want to demonstrate time-series optimisation.
 
---
 

## Component 4: Fusion Engine
 
Responsible for:
 

    Joining observations by time window
    Joining observations by geographic area
    Calculating aircraft dropout rates
    Calculating RF signal abnormalities
    Comparing current observations to baseline
    Producing fused anomaly records
    

Example fusion logic:
 

    Within a 15-minute window:
    - Count aircraft update gaps
    - Count RF noise spikes
    - Cluster observations geographically
    - Score whether evidence supports a disruption hypothesis
    

---
 

## Component 5: Anomaly Detection Engine
 
Responsible for:
 

    Detecting unusual RF readings
    Detecting aircraft track discontinuities
    Detecting sensor failure patterns
    Detecting source-level data issues
    

Initial methods:
 

    Threshold rules
    Rolling average
    Z-score
    DBSCAN for clustering
    Isolation Forest for anomaly scoring
    

---
 

## Component 6: Hypothesis Engine
 
Responsible for converting anomalies into explanations.
 
Each hypothesis should include:
 

    Title
    Description
    Confidence level
    Affected area
    Time window
    Supporting evidence
    Alternative explanations
    Recommended analyst action
    Status
    

Example statuses:
 

    New
    Under review
    Confirmed
    Rejected
    Inconclusive
    

---
 

## Component 7: FastAPI Backend
 
Responsible for:
 

    Serving data to frontend
    Providing WebSocket live updates
    Exposing API endpoints
    Receiving analyst feedback
    Triggering scenario generation
    Handling authentication in later versions
    

---
 

## Component 8: React Frontend
 
Suggested pages:
 

    Dashboard
    Map View
    Hypotheses
    Anomaly Timeline
    RF Observations
    Aircraft Tracks
    Scenario Control
    System Health
    

For MVP, the most important screens are:
 

    Map View
    Hypothesis Detail
    Timeline
    Scenario Control
    

---
 

# 10\. Frontend Wireframe Structure
 

## Main Dashboard Layout
 

     ------------------------------------------------------------
    | EM Fusion                                                   |
    |------------------------------------------------------------|
    | Scenario: GNSS Interference Sector A     System: Healthy    |
    |------------------------------------------------------------|
    |                            |                               |
    |        Geospatial Map       |   Hypotheses Panel            |
    |                            |   - Possible GNSS interference |
    |                            |   - Sensor outage              |
    |                            |   - API coverage gap           |
    |------------------------------------------------------------|
    | Timeline / Event Stream                                     |
    |------------------------------------------------------------|
    | Evidence Table                                              |
     ------------------------------------------------------------
    

## Hypothesis Detail Panel
 

    Hypothesis: Possible GNSS interference in Sector A
    
    Confidence: Medium
    Status: New
    
    Affected area:
    Sector A, 20 km radius
    
    Time window:
    12:10 - 12:25
    
    Evidence:
    1. RF noise spike detected by SNS-01 and SNS-03.
    2. Aircraft update rate dropped by 62%.
    3. Track discontinuities clustered in same region.
    
    Alternative explanations:
    - Data-source outage
    - Sensor malfunction
    - Normal traffic variation
    
    Analyst action:
    [Confirm] [Reject] [Needs more evidence] [Add note]
    

---
 

# 11\. Database Design
 

    erDiagram
        AIRCRAFT_TRACKS {
            int id
            string source
            string aircraft_id
            string callsign
            datetime timestamp
            float lat
            float lon
            float altitude
            float velocity
            float heading
            json metadata
        }
    
        RF_OBSERVATIONS {
            int id
            string sensor_id
            datetime timestamp
            float lat
            float lon
            float frequency_mhz
            string band
            float power_dbm
            float snr_db
            float bandwidth_khz
            string signal_type
            json metadata
        }
    
        ANOMALIES {
            int id
            string anomaly_type
            string severity
            datetime start_time
            datetime end_time
            string area_geojson
            float score
            json evidence
        }
    
        HYPOTHESES {
            int id
            string title
            string description
            string confidence_level
            string status
            datetime created_at
            string affected_area_geojson
            json evidence
            json alternatives
        }
    
        ANALYST_FEEDBACK {
            int id
            int hypothesis_id
            string decision
            string note
            datetime created_at
        }
    
        HYPOTHESES ||--o{ ANALYST_FEEDBACK : receives
    

---
 

# 12\. Suggested Tech Stack
 

## Frontend
 

    React
    TypeScript
    Vite
    React-Leaflet or Mapbox
    Zustand
    Recharts
    Tailwind or Material UI
    

## Backend
 

    Python
    FastAPI
    Pydantic
    SQLAlchemy
    Uvicorn
    WebSockets
    

## Data and Storage
 

    PostgreSQL
    PostGIS
    Optional TimescaleDB
    

## AI and Analytics
 

    Pandas
    NumPy
    Scikit-learn
    Optional PyTorch for RF/IQ classifier
    

## DevOps
 

    Docker
    Docker Compose
    GitHub Actions
    Trivy
    Pytest
    ESLint
    Black
    Ruff
    

## Deployment
 
Simple MVP deployment options:
 

    Local Docker Compose
    AWS EC2 with Docker Compose
    AWS ECS Fargate
    Render / Fly.io / Railway for simpler deployment
    

For my learning goals, I would recommend:
 

    Local Docker Compose first
    Then AWS EC2
    Then AWS ECS as stretch goal
    

---
 

# 13\. Deployment Architecture
 

    flowchart TB
        Dev[Developer Pushes Code] --> GH[GitHub Repository]
        GH --> CI[GitHub Actions Pipeline]
    
        CI --> Lint[Lint + Format Checks]
        CI --> Tests[Unit Tests]
        CI --> Build[Build Docker Images]
        CI --> Scan[Trivy Security Scan]
        CI --> Registry[Push Images to Container Registry]
    
        Registry --> Deploy[Deploy to Cloud Host]
    
        Deploy --> FE[Frontend Container]
        Deploy --> API[FastAPI Container]
        Deploy --> Worker[Ingestion Worker Container]
        Deploy --> DB[(PostgreSQL/PostGIS)]
    

---
 

# 14\. CI/CD Pipeline Scope
 
The GitHub Actions pipeline should include:
 

    Python linting
    Python tests
    Frontend linting
    Frontend tests
    Docker image build
    Security scanning with Trivy
    Optional deployment step
    

Example pipeline stages:
 

    1. Checkout code
    2. Set up Python
    3. Install backend dependencies
    4. Run backend tests
    5. Run backend linting
    6. Set up Node
    7. Install frontend dependencies
    8. Run frontend linting
    9. Build frontend
    10. Build Docker images
    11. Scan images
    12. Push images
    13. Deploy
    

This will make the project look much more professional.
 
---
 

# 15\. MVP User Stories
 

## Analyst User Stories
 

    As an analyst, I want to view aircraft tracks on a map so that I can understand movement patterns.
    
    As an analyst, I want to view RF observations on the same map so that I can compare movement anomalies with signal anomalies.
    
    As an analyst, I want to see generated hypotheses so that I can understand what the system believes may be happening.
    
    As an analyst, I want to inspect supporting evidence so that I can decide whether the hypothesis is credible.
    
    As an analyst, I want to confirm, reject, or mark a hypothesis as inconclusive so that human judgement is captured.
    

## Engineer User Stories
 

    As an engineer, I want a scenario generator so that I can reliably demo different contested-environment cases.
    
    As an engineer, I want API endpoints so that the fused data can be consumed by other systems.
    
    As an engineer, I want Docker Compose so that the whole system can be run locally.
    
    As an engineer, I want CI/CD checks so that code quality and security scanning are part of delivery.
    

---
 

# 16\. Non-Functional Requirements
 

## Reliability
 

    The system should support replay mode so demos do not depend entirely on live APIs.
    The backend should handle missing or incomplete data gracefully.
    The UI should clearly show when data is synthetic, replayed, or live.
    

## Explainability
 

    Every hypothesis must include supporting evidence.
    Every confidence level must be explainable.
    The system should show alternative explanations.
    

## Safety
 

    The system must not provide operational jamming instructions.
    The system must not claim to detect real hostile emitters.
    The system should be presented as a decision-support prototype.
    

## Security
 

    Use environment variables for API keys.
    Do not commit secrets.
    Run dependency and container scans.
    Validate all incoming data.
    Use CORS restrictions.
    

## Performance
 

    The MVP should support hundreds or low thousands of observations.
    WebSocket updates should be throttled if needed.
    The frontend should avoid rendering too many map markers at once.
    

---
 

# 17\. MVP Milestone Plan
 

## Milestone 1: Project Foundation
 
Deliverables:
 

    GitHub repository
    Backend folder
    Frontend folder
    Docker Compose file
    Basic FastAPI health endpoint
    Basic React app
    PostgreSQL container
    README skeleton
    

Outcome:
 

    The full app can run locally.
    

---
 

## Milestone 2: Data Model and Database
 
Deliverables:
 

    Aircraft tracks table
    RF observations table
    Anomalies table
    Hypotheses table
    Analyst feedback table
    Database migration setup
    Seed data
    

Outcome:
 

    The backend can store and retrieve core project data.
    

---
 

## Milestone 3: Scenario Generator
 
Deliverables:
 

    Normal scenario
    GNSS interference scenario
    Sensor outage scenario
    Aircraft dropout scenario
    Scenario reset endpoint
    Scenario start endpoint
    

Outcome:
 

    You can demo meaningful events without depending on live data.
    

---
 

## Milestone 4: Map Dashboard
 
Deliverables:
 

    React map
    Aircraft markers
    RF sensor markers
    Anomaly zone overlays
    Basic timeline
    

Outcome:
 

    Users can visually inspect the operational picture.
    

---
 

## Milestone 5: Anomaly and Hypothesis Engine
 
Deliverables:
 

    Rule-based anomaly detection
    Hypothesis generation
    Evidence generation
    Confidence levels
    Alternative explanations
    

Outcome:
 

    The system can generate explainable hypotheses.
    

---
 

## Milestone 6: Human Feedback
 
Deliverables:
 

    Hypothesis detail page
    Confirm/reject/inconclusive buttons
    Analyst notes
    Feedback storage
    Status updates
    

Outcome:
 

    The prototype demonstrates human-in-the-loop validation.
    

---
 

## Milestone 7: DevOps and Deployment
 
Deliverables:
 

    Dockerised services
    GitHub Actions pipeline
    Tests
    Linting
    Trivy scan
    Cloud deployment
    Architecture documentation
    Demo screenshots
    

Outcome:
 

    The project is portfolio-ready.
    

---
 

# 18\. Version 1 Success Criteria
 
The MVP is successful if you can demonstrate this flow:
 

    1. Start a scenario.
    2. Aircraft and RF data appear on the map.
    3. The system detects an anomaly.
    4. The system generates a hypothesis.
    5. The user opens the hypothesis and sees supporting evidence.
    6. The user confirms or rejects the hypothesis.
    7. The decision is stored.
    8. The full system runs through Docker Compose.
    9. CI/CD pipeline runs tests, builds images, and scans containers.
    

That is enough to make the project credible.
 
---
 

# 19\. Version 2 Roadmap
 
Version 2 is where we can add the more advanced features from your original idea.
 

## Version 2 Feature Area 1: Bayesian Hypothesis Updating
 
Add a proper probabilistic reasoning layer.
 
Instead of simple Low/Medium/High confidence, you could model how evidence changes belief over time.
 
Example:
 

    Hypothesis:
    Possible GNSS interference
    
    Evidence weights:
    - RF noise spike: strong support
    - Aircraft dropout: moderate support
    - Sensor disagreement: weakens confidence
    - Known exercise area: strengthens confidence
    

This would make the project more academically interesting.
 
---
 

## Version 2 Feature Area 2: Knowledge Graph
 
Introduce a knowledge graph for relationships between:
 

    Sensors
    Frequencies
    Signal types
    Geographic sectors
    Platforms
    Events
    Hypotheses
    Historical incidents
    Analyst feedback
    

Example:
 

    Sensor SNS-01 observed RF anomaly
    RF anomaly occurred in Sector A
    Sector A contains aircraft track dropouts
    Track dropouts support Hypothesis H-001
    Analyst confirmed Hypothesis H-001
    

Possible tools:
 

    Neo4j
    RDFLib
    NetworkX
    Graph database visualisation
    

---
 

## Version 2 Feature Area 3: Real RF Hardware Integration
 
Add optional software-defined radio integration.
 
Possible hardware:
 

    RTL-SDR
    HackRF
    USRP, if available
    

Use this carefully and safely. The aim should be passive spectrum observation, not transmission or interference.
 
Version 2 could support:
 

    Passive RF scan ingestion
    Spectrogram generation
    Power spectral density visualisation
    Basic modulation classification
    

---
 

## Version 2 Feature Area 4: Advanced AI Signal Classification
 
Improve the RF classifier.
 
Version 1 may only use simple features or a small model. Version 2 could include:
 

    CNN on spectrograms
    CNN/LSTM on IQ samples
    Transformer-based time-series classifier
    Model comparison dashboard
    Confidence calibration
    Explainability methods
    

The model should classify signal patterns, not make unsupported claims about military emitters.
 
---
 

## Version 2 Feature Area 5: LLM-Assisted Analyst Copilot
 
Add a controlled AI assistant inside the dashboard.
 
The assistant could answer:
 

    Why was this hypothesis generated?
    What evidence supports it?
    What evidence contradicts it?
    What happened in the last 15 minutes?
    Which sensors are unreliable?
    What alternative explanations exist?
    

The LLM should not be allowed to invent evidence. It should only summarise retrieved system data.
 
Architecture:
 

    User question
    → Retrieve relevant observations/hypotheses
    → Pass structured evidence to LLM
    → Generate grounded answer
    → Show citations/evidence references in UI
    

---
 

## Version 2 Feature Area 6: Model Evaluation and AI Assurance
 
This would be very valuable given your interest in AI testing and assurance.
 
Add evaluation metrics:
 

    Precision
    Recall
    False positive rate
    False negative rate
    Detection latency
    Confidence calibration
    Analyst agreement rate
    

Add test scenarios:
 

    True interference scenario
    False positive scenario
    Sensor failure scenario
    API outage scenario
    Mixed evidence scenario
    Ambiguous scenario
    

This turns the project from “AI demo” into a serious AI assurance prototype.
 
---
 

## Version 2 Feature Area 7: Multi-Source Data Fusion
 
Add more data sources:
 

    AIS vessel data
    Weather data
    Space weather data
    Satellite pass data
    NOTAM-style public aviation notices, if available
    Historical event replay
    

These should support alternative explanations.
 
For example:
 

    RF anomaly + aircraft dropout + solar storm data
    → Possible space-weather degradation
    
    RF anomaly + aircraft dropout + no environmental cause
    → Possible localised interference
    
    Aircraft dropout only + no RF anomaly
    → Possible data-source issue
    

---
 

## Version 2 Feature Area 8: Cloud-Native Deployment
 
Move from simple Docker Compose to a more production-like setup.
 
Possible upgrade path:
 

    Docker Compose
    → AWS EC2
    → AWS ECS Fargate
    → Terraform-managed infrastructure
    → Optional Kubernetes
    

Useful AWS services:
 

    ECS Fargate
    RDS PostgreSQL
    ECR
    CloudWatch
    S3
    API Gateway
    Lambda for lightweight ingestion
    EventBridge for scheduled jobs
    Secrets Manager
    

---
 

# 20\. Recommended Version 1 vs Version 2 Split
 

## Version 1: Build This First
 

    React dashboard
    FastAPI backend
    PostgreSQL/PostGIS
    Synthetic RF scenario generator
    Aircraft data ingestion or replay
    Rule-based anomaly detection
    Hypothesis generation
    Human feedback
    Docker Compose
    GitHub Actions
    Basic deployment
    

## Version 2: Add Later
 

    Bayesian inference
    Knowledge graph
    LLM analyst assistant
    Real SDR passive RF ingestion
    Advanced signal classifier
    AIS and weather/space-weather fusion
    Model evaluation dashboard
    Terraform and AWS ECS deployment
    Role-based access control
    Audit logging
    

---
 

# 21\. Final Recommended Project Structure
 

    em-fusion/
    │
    ├── backend/
    │   ├── app/
    │   │   ├── api/
    │   │   ├── core/
    │   │   ├── models/
    │   │   ├── schemas/
    │   │   ├── services/
    │   │   │   ├── ingestion/
    │   │   │   ├── fusion/
    │   │   │   ├── anomaly_detection/
    │   │   │   └── hypothesis/
    │   │   └── main.py
    │   ├── tests/
    │   ├── Dockerfile
    │   └── requirements.txt
    │
    ├── frontend/
    │   ├── src/
    │   │   ├── components/
    │   │   ├── pages/
    │   │   ├── maps/
    │   │   ├── stores/
    │   │   ├── api/
    │   │   └── App.tsx
    │   ├── Dockerfile
    │   └── package.json
    │
    ├── ai/
    │   ├── classifiers/
    │   ├── notebooks/
    │   ├── inference.py
    │   └── README.md
    │
    ├── scenarios/
    │   ├── normal_environment.json
    │   ├── gnss_interference_sector_a.json
    │   ├── sensor_failure.json
    │   └── api_dropout.json
    │
    ├── infrastructure/
    │   ├── docker-compose.yml
    │   ├── terraform/
    │   └── github-actions/
    │
    ├── docs/
    │   ├── architecture.md
    │   ├── data-model.md
    │   ├── threat-model.md
    │   ├── ai-assurance.md
    │   └── demo-script.md
    │
    └── README.md
    

---
 

# 22\. Best Final MVP Statement
 
Use this as the official scope statement:
 
> EM Fusion is a full-stack prototype for AI-assisted electromagnetic situational awareness. It fuses open aviation telemetry with synthetic RF sensor observations to detect anomalous spatiotemporal patterns, generate explainable hypotheses, and support human analyst validation through a geospatial dashboard. The MVP focuses on safe, non-operational decision support using simulated RF data, transparent evidence trails, and a containerised cloud-ready architecture.
 
This gives you a project that is ambitious, technically defensible, safe to present, and strong enough for a portfolio, workplace demo, or academic/professional development submission.