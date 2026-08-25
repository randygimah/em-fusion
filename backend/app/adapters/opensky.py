"""OpenSky replay adapter. Spec: adp-001.

STUB -- no implementation yet. Present so the test suite collects and each
test fails on its own assertion rather than on an import error, which is
what catches a test that would have passed against an empty module.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.dal.ingest import IngestResult
from app.dal.pseudonymise import Pseudonymiser
from app.dal.repository import ObservationRepository
from app.dal.validation import IngestContext

SOURCE_ID = "opensky-replay"


@dataclass(frozen=True)
class Window:
    """A half-open span of source time: [start, end)."""

    start: datetime
    end: datetime


def available_window(manifest: Mapping[str, Any]) -> Window:
    raise NotImplementedError("adp-001")


def read_window(path: Path, window: Window) -> Iterator[Mapping[str, Any]]:
    raise NotImplementedError("adp-001")


def replay_window(
    path: Path,
    window: Window,
    context: IngestContext,
    repository: ObservationRepository,
    pseudonymiser: Pseudonymiser,
) -> IngestResult:
    raise NotImplementedError("adp-001")
