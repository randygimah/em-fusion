"""Reading the frontend's TypeScript contracts from the backend suite.

Extracted 2026-09-13 when `scn-004` needed the same parser `api-002` wrote.
Two copies of a parser is two places for the rule to drift while both suites
stay green, which is the failure mode the parity tests exist to prevent one
level down.

A **parser**, never a search. Looking for a field name anywhere in the file is
satisfied by a comment mentioning it -- the defect recorded in `docs/qa.md`
section 38, hit again in `adp-007`, and again in `scn-003`'s Makefile check.

Every reader here **raises rather than skips** when a contract is missing.
`frontend/` is not mounted into the backend container by default, and a skip
would turn every assertion below it into a silent pass, which is the failure
one level up (`ops-003`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Native checkout first, then the read-only mount used inside the container.
CONTRACT_ROOTS = (REPO_ROOT / "frontend", Path("/repo/frontend"))


def contract_paths(name: str) -> tuple[Path, ...]:
    """Where a contract file may be, in the order to look."""
    return tuple(root / "src" / "types" / name for root in CONTRACT_ROOTS)


def read_contract(candidates: Sequence[Path]) -> str:
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(
        f"not found at any of {[str(p) for p in candidates]}. Skipping is "
        "deliberately not an option here: see the module docstring."
    )


def interfaces(source: str) -> dict[str, dict[str, str]]:
    """Every `export interface` in a contract, as name to field to type."""
    found: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r"export\s+interface\s+(\w+)\s*\{(.*?)\n\}", source, re.DOTALL
    ):
        name, body = match.group(1), match.group(2)
        fields: dict[str, str] = {}
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            field = re.match(r"(\w+)\??\s*:\s*(.+?);\s*$", line)
            if field:
                fields[field.group(1)] = field.group(2).strip()
        found[name] = fields
    return found


def union_members(source: str, name: str) -> tuple[str, ...]:
    """The string literals of an exported union type, in declaration order.

    `export type ScenarioTypeId = "normal-baseline" | ...;` is how the closed
    set of scenario types reaches the frontend, and a closed set that is not
    compared against its origin is a list someone edits one side of.
    """
    match = re.search(
        rf"export\s+type\s+{re.escape(name)}\s*=\s*(.*?);", source, re.DOTALL
    )
    if match is None:
        raise AssertionError(f"the contract declares no union type named {name!r}")
    return tuple(re.findall(r'"([^"]+)"', match.group(1)))


def const_object(source: str, name: str) -> dict[str, str]:
    """An exported const object's fields, as name to the literal source text.

    Values are returned unparsed: `null` and `"narrowband"` and `900` are
    compared by the caller, which knows which is which. Parsing them here would
    mean deciding what a TypeScript literal means in Python in a helper nobody
    is looking at.
    """
    match = re.search(
        rf"export\s+const\s+{re.escape(name)}[^=]*=\s*\{{(.*?)\n\}}", source, re.DOTALL
    )
    if match is None:
        raise AssertionError(f"the contract declares no const object named {name!r}")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        field = re.match(r"(\w+)\s*:\s*(.+?),?\s*$", line)
        if field:
            fields[field.group(1)] = field.group(2).strip().rstrip(",")
    return fields
