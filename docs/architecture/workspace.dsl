workspace "EM Fusion" "Explainable electromagnetic situational awareness: a human-in-the-loop decision-support prototype." {

    !identifiers flat

    model {
        !impliedRelationships true

        analyst = person "Analyst" "Reviews the fused picture, judges machine-generated hypotheses, and records a verdict. The terminal node of every decision path — the system recommends, the analyst decides." "Human"

        openSky = softwareSystem "Archived OpenSky Corpus" "A one-hour extract of ADS-B state vectors, filtered to a fixed bounding box and committed to the repository as Parquet with its provenance manifest. Replayed, never queried live, so the pipeline reproduces from a fresh clone with no download step." "External,Data"

        hostedAi = softwareSystem "Hosted AI Provider" "Frontier LLM reached over HTTPS with native JSON-schema-constrained output. The primary hypothesis-generation arm, and the project's sole hosted dependency and sole running cost." "External,AI"

        localModel = softwareSystem "Local Model Server" "Open-weight model served natively on the host (Ollama / llama-cpp) with GBNF grammar constraint. Runs as a host process rather than a Compose service because Docker Desktop on macOS does not pass Metal through. Availability fallback and offline-demo guarantee; not scored." "External,AI,Host Process"

        tiles = softwareSystem "Basemap Tile Source" "Free raster/vector tiles fetched directly by the browser. Configured by URL; MapView degrades to a labelled placeholder when unset." "External,Optional"

        emFusion = softwareSystem "EM Fusion" "Fuses replayed aviation telemetry and synthetic RF observations, detects deviations deterministically, and turns evidence bundles into schema-validated, grounding-checked hypotheses for human review." {

            dashboard = container "Analyst Dashboard" "Three screens — Operational Picture, Hypotheses, Scenario Control. Dumb renderers over a typed contract; built assets served by nginx, executed in the browser. Confidence renders as Low/Medium/High only, never a number." "React, TypeScript, Vite, Tailwind, MapLibre GL JS" "Browser"

            db = container "Observation Store" "Canonical observations with provenance, anomaly events, evidence bundles, hypotheses (with generator, model_id, generation_params, raw_response), analyst feedback, and seeded scenario runs. PostGIS earns its place on one real spatial query: track discontinuities within N km of an RF anomaly zone." "PostgreSQL + PostGIS" "Database"

            harness = container "Scenario Runner & Evaluation Harness" "Batch entrypoint into the same image as the backend, invoked from the root Makefile. Executes seeded scenario runs, computes detection metrics in simulated time, and emits the anonymised scoring pack. Reads scenario_runs.ground_truth to score, and never exposes it downstream." "Python CLI, Pandas/NumPy" "CLI"

            api = container "Backend API" "Serves the operational picture and hypotheses to the dashboard by polling, and hosts the ingestion, detection, and hypothesis pipeline. No push channel, by decision." "Python, FastAPI, Uvicorn, SQLAlchemy, Pydantic" {

                routes = component "API Routes" "/health, /operational-picture (view filter, suppressed counts), /hypotheses, /aircraft/track-window (server-bounded, truncation reported), /feedback, /scenario. No SQL or spatial logic here." "FastAPI routers"

                scenarioGenerator = component "Scenario Generator" "Parameterised by scenario type, noise amplitude, gap duration, sensor count, area, timing, and seed. Every run reproducible from its seed — the foundation the evaluation harness stands on." "Python"

                aviationAdapter = component "Aviation Adapter" "Adapter 1. Replays archived ADS-B state vectors into source-shaped records." "Python" "Adapter Seam"

                rfAdapter = component "RF Adapter" "Adapter 2. Synthesises observations on the full sensor x channel x interval grid — 6-8 sensors, 8 x 2 MHz channels spanning 1567.42-1581.42 MHz with one centred on GNSS L1. Every sensor reports every channel every interval, so a missing reading is a detectable gap rather than an ambiguous absence." "Python" "Adapter Seam"

                thirdAdapter = component "Third Source Adapter" "Late-project extensibility demonstration (RQ1). Added after the pipeline is frozen; files touched, lines changed, and hours taken are the measurement." "Python" "Adapter Seam,Planned"

                dal = component "Data Abstraction Layer" "The seam the extensibility claim rests on. Maps any source-shaped record to the canonical observation model, validates required fields, quarantines malformed records rather than dropping them, and attaches provenance to every record that survives." "Python, Pydantic" "Seam"

                repositories = component "Repositories" "All SQL and spatial logic. Keeps PostGIS out of route handlers and out of the engines." "Python, SQLAlchemy, PostGIS"

                baselineEngine = component "Baseline Engine" "Rolling averages over normal-scenario runs, computed per sensor per channel. Pooling channels into one per-sensor baseline would hide single-channel deviations inside the spread of the others." "Python"

                anomalyEngine = component "Anomaly Detection Engine" "Deterministic only: threshold rules, z-score deviation, PostGIS spatial clustering, and a frequency-adjacency test that separates a faulty sensor from a degraded environment. No Isolation Forest, no DBSCAN." "Python"

                bundleBuilder = component "Evidence Bundle Builder" "Groups anomalies on three axes — time window, spatial proximity, and frequency adjacency — and attaches source lineage, rule IDs, and known uncertainties. Grouping on time and space alone would fragment one broadband event into eight unrelated findings." "Python"

                hypothesisService = component "Hypothesis Service" "Provider-agnostic: the interface is evidence_bundle -> validated hypothesis, and provider, model ID, and generation params come from config. Written before either provider so neither provider's shape leaks into it. The second seam carrying the RQ1 extensibility argument." "Python" "Seam"

                templateGenerator = component "Template Generator" "Deterministic, no model dependency. Both the correctness fallback and the evaluation baseline that the hosted arm is scored against." "Python" "Generator"

                hostedGenerator = component "Hosted Generator" "Primary arm. Native JSON-schema-constrained output, so conformance is a generation-time guarantee rather than a post-hoc check. Dated model ID, never a moving alias." "Python" "Generator"

                localGenerator = component "Local Generator" "Second consumer of the service interface. Same schema, enforced by GBNF grammar instead — one schema, two enforcement mechanisms. Availability fallback only; time-boxed and droppable." "Python" "Generator"

                schemaValidation = component "Schema Validation" "Pydantic gate on every generated hypothesis. Confidence is Low/Medium/High by construction — anything else is unrepresentable, not merely rejected." "Python, Pydantic" "Guard"

                groundingCheck = component "Grounding Check" "Every supporting-evidence item must trace back to an item in the originating bundle. Ungrounded hypotheses are flagged or rejected, and the catch rate is logged per arm as a reportable result." "Python" "Guard"
            }
        }

        # --- People -------------------------------------------------------

        analyst -> dashboard "Reviews the picture and hypotheses; confirms, rejects, requests more evidence, or marks a false positive"

        # --- Frontend -----------------------------------------------------

        dashboard -> routes "Polls the operational picture, hypotheses, and track windows; posts analyst verdicts" "JSON/HTTP — polling, no WebSockets"
        dashboard -> tiles "Fetches basemap tiles, from inside the MapView boundary only" "HTTPS"

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

        bundleBuilder -> hypothesisService "Submits an evidence bundle — structured evidence only, never the scenario type"
        hypothesisService -> hostedGenerator "Primary path"
        hypothesisService -> localGenerator "Availability fallback — hosted unreachable"
        hypothesisService -> templateGenerator "Correctness fallback — schema or grounding failure after bounded retry"
        hostedGenerator -> hostedAi "Schema-constrained generation" "HTTPS, dated model ID, temperature 0"
        localGenerator -> localModel "Grammar-constrained generation" "HTTP via host.docker.internal"
        hypothesisService -> schemaValidation "Submits generated output"
        schemaValidation -> groundingCheck "Passes parsed hypotheses"
        groundingCheck -> repositories "Persists the hypothesis with generator, model_id, generation_params, raw_response, and grounding_passed"

        # --- Serving ------------------------------------------------------

        routes -> repositories "Reads the fused picture and hypotheses; persists verdicts and status changes"
        repositories -> db "Reads and writes" "SQLAlchemy / SQL + PostGIS"

        # --- Batch --------------------------------------------------------

        harness -> scenarioGenerator "Executes randomised seeded runs per scenario type"
        harness -> hypothesisService "Generates the scored corpus over identical bundles (hosted and template arms)"
        harness -> repositories "Reads runs, anomalies, and hypotheses to compute metrics in simulated time"

        # --- Deployment ---------------------------------------------------

        deploymentEnvironment "Local Docker Compose" {

            laptop = deploymentNode "Development Machine" "The v1 deployment target. Cloud is future work." "macOS" {

                browser = deploymentNode "Web Browser" "" "Chromium / Firefox" {
                    containerInstance dashboard
                }

                docker = deploymentNode "Docker Desktop" "Everything inside this boundary comes up with `make demo`." "Docker Engine + Compose" {

                    deploymentNode "frontend" "Serves the built SPA bundle." "nginx" {
                    }

                    deploymentNode "backend" "" "python:slim, Uvicorn" {
                        containerInstance api
                    }

                    deploymentNode "db" "" "postgis/postgis" {
                        containerInstance db
                    }

                    deploymentNode "runner" "Ephemeral — `docker compose run`, not a long-lived service." "python:slim" {
                        containerInstance harness
                    }
                }

                ollama = deploymentNode "Model Server" "Deliberately outside Compose: Docker Desktop on macOS does not pass Metal through, so a containerised runtime would silently fall back to CPU. Reached at host.docker.internal — a config value, not a service." "Ollama, native host process" {
                    softwareSystemInstance localModel
                }
            }
        }
    }

    views {

        systemContext emFusion "L1_SystemContext" "Level 1 — the analyst is the terminal node. EM Fusion is decision support, not autonomous decision-making." {
            include *
            autoLayout lr
        }

        container emFusion "L2_Containers" "Level 2 — note the polling edge from dashboard to API: the absence of a push channel is a decision, not an omission. The local model server sits outside the system boundary because it runs on the host, not in Compose." {
            include *
            autoLayout lr
        }

        component api "L3_BackendComponents" "Level 3 — backend only. The two highlighted seams are the RQ1 extensibility argument: any source reaches the canonical model through the DAL, and any generator reaches the analyst through the provider-agnostic hypothesis service and the two guards behind it." {
            include *
            autoLayout lr
        }

        deployment emFusion "Local Docker Compose" "Deployment" "What comes up with `make demo`, and what deliberately does not." {
            include *
            autoLayout lr
        }

        styles {
            element "Element" {
                shape RoundedBox
                background #1f6feb
                color #ffffff
                stroke #0d2b52
            }
            element "Human" {
                shape Person
                background #26343f
            }
            element "Software System" {
                background #14507a
            }
            element "Container" {
                background #1f6feb
            }
            element "Component" {
                background #4a90d9
            }
            element "External" {
                background #55606b
                color #ffffff
            }
            element "Database" {
                shape Cylinder
                background #2f6f4f
            }
            element "Browser" {
                shape WebBrowser
            }
            element "CLI" {
                shape Pipe
                background #6b4fa8
            }
            element "Seam" {
                background #b8860b
                stroke #5c4406
            }
            element "Adapter Seam" {
                background #c99a1e
                stroke #5c4406
            }
            element "Generator" {
                background #7a4fa8
            }
            element "Guard" {
                background #a03d3d
            }
            element "Planned" {
                opacity 45
                border dashed
            }
            element "Optional" {
                opacity 60
                border dashed
            }
            relationship "Relationship" {
                thickness 2
                color #94a3b8
            }
        }

        # No `theme default`: it fetches from Structurizr's cloud service (EOL 30 Sep 2026),
        # which would make the diagrams un-regenerable and add a hosted dependency the project
        # does not otherwise carry. The styles above are self-contained.
    }
}
