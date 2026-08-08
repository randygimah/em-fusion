workspace "EM Fusion" "Explainable electromagnetic situational awareness: a human-in-the-loop decision-support prototype." {

    // Rationale for these modelling choices lives in docs/thesis_notes.md
    // (System Design and Architecture); technical detail in docs/em_fusion_v2.md.
    // Keep descriptions here to one short line.

    !identifiers flat

    model {
        !impliedRelationships true

        analyst = person "Analyst" "Judges hypotheses and records a verdict. The terminal node of every decision path." "Human"

        openSky = softwareSystem "Archived OpenSky Corpus" "One hour of ADS-B state vectors, committed as Parquet and replayed." "External,Data"

        hostedAi = softwareSystem "Hosted AI Provider" "Frontier LLM with schema-constrained output. The primary generation arm." "External,AI"

        localModel = softwareSystem "Local Model Server" "Open-weight model on the host. Availability fallback only; absent from L1 and L2 by design." "External,AI,Fallback"

        emFusion = softwareSystem "EM Fusion" "Fuses replayed telemetry and synthetic RF, detects deviations deterministically, and turns evidence into validated hypotheses." {

            dashboard = container "Analyst Dashboard" "Three screens. Polls the API; confidence renders Low/Medium/High only." "React, TypeScript, Vite, MapLibre GL JS" "Browser"

            tiles = container "Basemap Tile Archive" "Self-hosted vector basemap for the project bounding box, served as a static file by the frontend nginx." "PMTiles, OpenStreetMap (ODbL)" "Data,Optional"

            db = container "Observation Store" "Observations with provenance, anomalies, bundles, hypotheses, feedback, scenario runs." "PostgreSQL + PostGIS" "Database"

            harness = container "Scenario Runner & Evaluation Harness" "Batch entrypoint into the backend image. Runs seeded scenarios and computes metrics." "Python CLI, Pandas/NumPy" "CLI"

            api = container "Backend API" "Serves the picture and hypotheses by polling; hosts the ingestion, detection, and hypothesis pipeline." "Python, FastAPI, Uvicorn, SQLAlchemy" {

                routes = component "API Routes" "Request handling only. No SQL, no spatial logic." "FastAPI routers"

                scenarioGenerator = component "Scenario Generator" "Parameterised and seeded; every run reproducible from its seed." "Python"

                aviationAdapter = component "Aviation Adapter" "Adapter 1. Replays archived ADS-B state vectors." "Python" "Adapter Seam"

                rfAdapter = component "RF Adapter" "Adapter 2. Synthesises the full sensor x channel x interval grid." "Python" "Adapter Seam"

                thirdAdapter = component "Third Source Adapter" "Late extensibility demonstration (RQ1)." "Python" "Adapter Seam,Planned"

                dal = component "Data Abstraction Layer" "Maps any source to the canonical model; validates, quarantines, attaches provenance." "Python, Pydantic" "Seam"

                repositories = component "Repositories" "All SQL and spatial logic." "Python, SQLAlchemy, PostGIS"

                baselineEngine = component "Baseline Engine" "Rolling averages, per sensor per channel." "Python"

                anomalyEngine = component "Anomaly Detection Engine" "Deterministic only: thresholds, z-score, spatial clustering, frequency adjacency." "Python"

                bundleBuilder = component "Evidence Bundle Builder" "Groups anomalies on time, space, and frequency; attaches lineage and uncertainties." "Python"

                hypothesisService = component "Hypothesis Service" "Provider-agnostic: evidence bundle to validated hypothesis. Provider and params from config." "Python" "Seam"

                templateGenerator = component "Template Generator" "Deterministic. Correctness fallback and evaluation baseline." "Python" "Generator"

                hostedGenerator = component "Hosted Generator" "Primary arm. Native JSON-schema-constrained output." "Python" "Generator"

                localGenerator = component "Local Generator" "Availability fallback. Same schema, enforced by GBNF grammar." "Python" "Generator,Fallback"

                schemaValidation = component "Schema Validation" "Pydantic gate. Confidence is Low/Medium/High by construction." "Python, Pydantic" "Guard"

                groundingCheck = component "Grounding Check" "Every evidence item must trace to the bundle. Catch rate logged per arm." "Python" "Guard"
            }
        }

        # --- People -------------------------------------------------------

        analyst -> dashboard "Reviews hypotheses; confirms, rejects, requests evidence, or marks a false positive"

        # --- Frontend -----------------------------------------------------

        dashboard -> routes "Polls the picture, hypotheses, and track windows; posts verdicts" "JSON/HTTP — polling, no WebSockets"
        dashboard -> tiles "Fetches basemap tiles, from inside the MapView boundary only" "HTTP range requests"

        # --- Ingestion ----------------------------------------------------

        scenarioGenerator -> aviationAdapter "Drives a seeded run"
        scenarioGenerator -> rfAdapter "Drives a seeded run"
        aviationAdapter -> openSky "Replays archived state vectors" "Parquet, local file"
        aviationAdapter -> dal "Emits source-shaped records"
        rfAdapter -> dal "Emits source-shaped records"
        thirdAdapter -> dal "Emits source-shaped records"
        dal -> repositories "Canonical observations with provenance; malformed records quarantined"

        # --- Detection ----------------------------------------------------

        baselineEngine -> repositories "Reads normal-scenario windows"
        anomalyEngine -> baselineEngine "Compares a window against the per-sensor per-channel baseline"
        anomalyEngine -> repositories "Reads observation windows; writes anomaly events"
        bundleBuilder -> repositories "Reads anomalies; writes evidence bundles"

        # --- Hypothesis layer ---------------------------------------------

        bundleBuilder -> hypothesisService "Submits a bundle — evidence only, never the scenario type"
        hypothesisService -> hostedGenerator "Primary path"
        hypothesisService -> localGenerator "Availability fallback — hosted unreachable"
        hypothesisService -> templateGenerator "Correctness fallback — schema or grounding failure after bounded retry"
        hostedGenerator -> hostedAi "Schema-constrained generation" "HTTPS, dated model ID"
        localGenerator -> localModel "Grammar-constrained generation" "HTTP via host.docker.internal"
        hypothesisService -> schemaValidation "Submits generated output"
        schemaValidation -> groundingCheck "Passes parsed hypotheses"
        groundingCheck -> repositories "Persists the hypothesis with generator, model_id, params, and raw_response"

        # --- Serving ------------------------------------------------------

        routes -> repositories "Reads the fused picture and hypotheses; persists verdicts"
        repositories -> db "Reads and writes" "SQL + PostGIS"

        # --- Batch --------------------------------------------------------

        harness -> scenarioGenerator "Executes randomised seeded runs"
        harness -> hypothesisService "Generates the scored corpus (hosted and template arms)"
        harness -> repositories "Reads runs, anomalies, and hypotheses to compute metrics"

        # --- Deployment ---------------------------------------------------

        deploymentEnvironment "Local Docker Compose" {

            laptop = deploymentNode "Development Machine" "The v1 deployment target." "macOS" {

                browser = deploymentNode "Web Browser" "" "Chromium / Firefox" {
                    containerInstance dashboard
                }

                docker = deploymentNode "Docker Desktop" "Comes up with `make demo`." "Docker Engine + Compose" {

                    deploymentNode "frontend" "Serves the SPA bundle and the tile archive." "nginx" {
                        containerInstance tiles
                    }

                    deploymentNode "backend" "" "python:slim, Uvicorn" {
                        containerInstance api
                    }

                    deploymentNode "db" "" "postgis/postgis" {
                        containerInstance db
                    }

                    deploymentNode "runner" "Ephemeral — `docker compose run`." "python:slim" {
                        containerInstance harness
                    }
                }

                ollama = deploymentNode "Model Server" "Outside Compose: Docker Desktop on macOS does not pass Metal through. A config value, not a service." "Ollama, native host process" {
                    softwareSystemInstance localModel
                }
            }
        }
    }

    views {

        systemContext emFusion "L1_SystemContext" "Level 1 — the analyst is the terminal node. EM Fusion is decision support, not autonomous decision-making. The hosted AI provider is the only system EM Fusion depends on over a network." {
            include *
            exclude localModel
            autoLayout lr
        }

        container emFusion "L2_Containers" "Level 2 — the polling edge from dashboard to API is deliberate: there is no push channel. The local model server is excluded here; it is a fallback internal to the hypothesis service, shown at L3." {
            include *
            exclude localModel
            autoLayout lr
        }

        component api "L3_BackendComponents" "Level 3 — backend only. The highlighted seams carry the RQ1 extensibility argument: any source reaches the canonical model through the DAL, and any generator reaches the analyst through the hypothesis service and the two guards behind it." {
            include *
            autoLayout lr
        }

        deployment emFusion "Local Docker Compose" "Deployment" "What comes up with `make demo`, and what deliberately does not." {
            include *
            autoLayout lr
        }

        # Palette taken from DESIGN.md tokens so the figures and the UI read as one system.
        styles {
            element "Element" {
                shape RoundedBox
                background #1d2027
                color #e1e2ec
                stroke #424754
                strokeWidth 2
            }
            element "Human" {
                shape Person
                background #32353c
                color #e1e2ec
            }
            element "Software System" {
                background #272a31
                color #e1e2ec
            }
            element "External" {
                background #8c909f
                color #10131a
                stroke #424754
            }
            element "Container" {
                background #1d2027
                color #e1e2ec
            }
            element "Component" {
                background #32353c
                color #e1e2ec
            }
            element "Database" {
                shape Cylinder
                background #03b5d3
                color #00232b
                stroke #003640
            }
            element "Data" {
                shape Folder
                background #4cd7f6
                color #00232b
                stroke #003640
            }
            element "Browser" {
                shape WebBrowser
            }
            element "CLI" {
                shape Pipe
            }
            element "Seam" {
                background #df7412
                color #2b1200
                stroke #502400
                strokeWidth 4
            }
            element "Adapter Seam" {
                background #ffb786
                color #2b1200
                stroke #502400
                strokeWidth 4
            }
            element "Generator" {
                background #4d8eff
                color #00285d
                stroke #002e6a
            }
            element "Guard" {
                background #93000a
                color #ffdad6
                stroke #690005
            }
            element "Planned" {
                opacity 45
                border dashed
            }
            element "Optional" {
                opacity 70
                border dashed
            }
            element "Fallback" {
                opacity 60
                border dashed
            }
            # Deployment nodes are containers for other elements, not elements in their own
            # right — near-white so the things inside them carry the colour.
            element "Deployment Node" {
                background #f4f6fa
                color #2e3038
                stroke #8c909f
                strokeWidth 2
            }
            relationship "Relationship" {
                thickness 2
                color #6b7280
                fontSize 22
            }
        }

        # No `theme default`: it fetches from Structurizr's cloud service (EOL 30 Sep 2026),
        # which would make the diagrams un-regenerable and add a hosted dependency the project
        # does not otherwise carry. The styles above are self-contained.
    }
}
