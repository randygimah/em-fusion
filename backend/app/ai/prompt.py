"""THROWAWAY STUB -- proving the tests red."""

from __future__ import annotations

import hashlib

HYPOTHESIS_PROMPT = "stub"


def prompt_fingerprint() -> str:
    return hashlib.sha256(HYPOTHESIS_PROMPT.encode("utf-8")).hexdigest()
