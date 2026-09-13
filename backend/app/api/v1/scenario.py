"""STUB, written at the test stage. Spec: api-006.

Deliberately not the implementation. It exists so `tests/test_api_scenario.py`
can import `get_batch_launcher` and reach real routes, which gives every test
in that file its own verdict instead of one collection error — the step
`scn-005` skipped and paid for.

Replaced wholesale at the code stage.
"""

from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter

router = APIRouter(prefix="/scenario", tags=["scenario"])


class BatchLauncher(Protocol):
    def __call__(self, request: Any) -> None: ...


def get_batch_launcher() -> BatchLauncher:
    raise NotImplementedError("get_batch_launcher: not implemented (api-006)")


@router.post("/start", status_code=202)
def start_scenario() -> dict[str, Any]:
    raise NotImplementedError("POST /scenario/start: not implemented (api-006)")


@router.get("/runs")
def list_scenario_runs() -> list[dict[str, Any]]:
    raise NotImplementedError("GET /scenario/runs: not implemented (api-006)")
