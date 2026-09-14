"""Detection: baselines, deterministic detectors, and evidence bundles.

Phase 8. Nothing here reaches a database or a network -- detectors take
observations and return findings, and fetching is the repository's job.
That separation is what lets the arithmetic be tested without Docker, and
what keeps `FR-904`'s rule about where SQL lives true one layer further up.
"""
