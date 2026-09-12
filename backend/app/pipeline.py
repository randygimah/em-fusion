"""Stub. Spec: scn-003 (pass 1 of 2) — tests written, implementation not yet.

Present so the suite collects and every test fails on its own assertion rather
than on one collection error, which is the practice `scn-001` left behind.
"""

from __future__ import annotations

from typing import Any

#: The run count a batch must fall within (`scn-003`, FR-205).
MIN_RUNS = 20
MAX_RUNS = 30


def derive_seeds(base_seed: int, count: int) -> tuple[int, ...]:
    raise NotImplementedError("scn-003 is not implemented yet")


def derive_window(corpus: Any, seed: int, duration_seconds: int) -> Any:
    raise NotImplementedError("scn-003 is not implemented yet")
