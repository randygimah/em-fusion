"""The evidence behind an hour's reported claims. Spec: api-015.

Stub: `api-015` is specified and unbuilt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.detection.bundle import EvidenceBundle
from app.detection.control import REGISTER, Key, Producer
from app.detection.findings import DetectionFinding

NOT_BUNDLED = "not-bundled"
NO_CURRENT_CLAIM = "no-current-claim"


class EvidenceError(ValueError):
    """A stored bundle this payload refuses to serve."""


class EvidenceAccount:  # type: ignore[no-redef]
    """Stub."""


def build_evidence_account(
    *,
    run_id: int,
    findings: Sequence[DetectionFinding],
    bundles: Sequence[tuple[int, EvidenceBundle]],
    register: Mapping[Key, Producer] = REGISTER,
) -> Any:
    """Stub: `api-015` is specified and unbuilt."""
    raise NotImplementedError("api-015")
