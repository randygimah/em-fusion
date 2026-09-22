"""THROWAWAY STUB -- proving the tests red."""

from __future__ import annotations

import json
from typing import Any

from app.detection.bundle import EvidenceBundle

BUNDLE_EXCLUDED = frozenset({"scenario_run_id"})
ITEM_EXCLUDED = frozenset({"observation_ids"})


def bundle_payload(bundle: EvidenceBundle) -> dict[str, Any]:
    return {"anomaly_type": bundle.anomaly_type, "evidence": [{}], "superseded": []}


def payload_json(bundle: EvidenceBundle) -> str:
    return json.dumps(bundle_payload(bundle))
