"""The root Makefile as the containerised command surface. Spec: ops-003.

These tests read the Makefile and assert its structure. That is a weaker kind
of evidence than running the targets, and the limit is worth stating: a target
can be well-formed and still fail against a real Docker daemon. What these
catch is the class of defect that has actually occurred in this project --
a target that silently does less than its name claims. `test-backend` ran with
`--no-deps` for weeks, which starts the backend container alone, so every
database test would have skipped while the target reported success.

The Makefile lives at the repository root, which is **not** mounted into the
backend container: Compose mounts `./backend:/app`. Rather than let these skip
in the containerised run -- the one this item calls authoritative -- the
`test-backend` target mounts the file read-only at `/repo/Makefile`, following
the pattern `generate` already uses for `DATA_DIR`. A skip here would be the
same failure mode the tests exist to catch, one level up.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: Native checkout, then the read-only mount used inside the container.
CANDIDATE_PATHS = (
    Path(__file__).resolve().parents[2] / "Makefile",
    Path("/repo/Makefile"),
)

#: Enumerated by ops-003. The item's own text says that enumerating them is
#: what makes it the thing to amend whenever one is added -- so this set is the
#: enforcement of that sentence rather than a restatement of it.
REQUIRED_TARGETS = {
    "build",
    "up",
    "down",
    "demo",
    "generate",
    "migrate",
    "db-test-create",
    # spec: adp-007 -- added 2026-09-04 with the replay entrypoint. ops-003's
    # own text makes this set the enforcement of "this item enumerates its
    # targets", so a new target lands here and not only in the Makefile.
    "replay",
    # spec: scn-003 -- added 2026-09-12 with the batch runner. `generate` is
    # the one target that had no build prerequisite, and the pipeline service
    # builds its own image rather than sharing the backend's, so a stale image
    # ran yesterday's dependencies against today's code.
    "build-pipeline",
    "test",
    "test-backend",
    "test-frontend",
}

#: Tools that would mean the root Makefile needs a host toolchain beyond
#: Docker. Each may appear only inside a compose invocation.
HOST_TOOLCHAIN = ("uv ", "pnpm ", "pytest ", "npm ", "node ", "alembic ", "black ")


def _makefile() -> str:
    for path in CANDIDATE_PATHS:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise AssertionError(  # pragma: no cover -- a broken checkout or mount
        f"root Makefile not found at any of {[str(p) for p in CANDIDATE_PATHS]}. "
        "Skipping is deliberately not an option here: see the module docstring."
    )


def _recipes() -> dict[str, list[str]]:
    """Target name to its recipe lines, with backslash continuations joined."""
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    pending = ""

    for raw in _makefile().splitlines():
        if raw.startswith("\t"):
            if current is None:
                continue
            pending += raw.strip()
            if pending.endswith("\\"):
                pending = pending[:-1] + " "
                continue
            recipes[current].append(pending)
            pending = ""
            continue

        pending = ""
        match = re.match(r"^([A-Za-z0-9_-]+)\s*:(?!=)", raw)
        current = match.group(1) if match else None
        if current is not None:
            recipes.setdefault(current, [])

    return recipes


def _phony_targets() -> set[str]:
    text = _makefile()
    declared: set[str] = set()
    for match in re.finditer(r"^\.PHONY:(.*?)(?=^\S|\Z)", text, re.M | re.S):
        declared.update(match.group(1).replace("\\", " ").split())
    return declared


# ------------------------------------------------------------------- targets


@pytest.mark.parametrize("target", sorted(REQUIRED_TARGETS))
def test_every_enumerated_target_exists(target: str) -> None:
    # spec: ops-003
    assert target in _recipes()


@pytest.mark.parametrize("target", sorted(REQUIRED_TARGETS))
def test_every_enumerated_target_is_phony(target: str) -> None:
    # spec: ops-003 -- without .PHONY, a target sharing a name with a file or
    # directory silently does nothing and reports success
    assert target in _phony_targets()


def test_migrate_applies_the_alembic_revisions() -> None:
    # spec: ops-003, db-001
    recipe = " ".join(_recipes()["migrate"])

    assert "alembic upgrade head" in recipe
    assert "$(COMPOSE)" in recipe


# ----------------------------------------------------- the database tier runs


def test_test_backend_does_not_use_no_deps() -> None:
    # spec: ops-003 -- the named failure case, and a real regression: --no-deps
    # starts the backend container alone, so postgis never comes up and every
    # database test skips while the target reports success
    assert "--no-deps" not in " ".join(_recipes()["test-backend"])


def test_test_backend_supplies_a_test_database_url() -> None:
    # spec: ops-003, db-001 -- without it the database tier skips, which is the
    # second failure case
    assert "TEST_DATABASE_URL" in " ".join(_recipes()["test-backend"])


def test_test_backend_provisions_the_test_database_first() -> None:
    # spec: ops-003 -- the database must exist before the tests address it, and
    # depending on the target is what stops that being a manual step nobody
    # wrote down (AC-12)
    prerequisites = re.search(r"^test-backend\s*:([^\n#]*)", _makefile(), re.M)

    assert prerequisites is not None
    assert "db-test-create" in prerequisites.group(1)


def test_db_test_create_is_idempotent_and_installs_postgis() -> None:
    # spec: ops-003, db-001 -- run twice it must not fail, and the extension is
    # what db-001's migrations assert rather than create
    recipe = " ".join(_recipes()["db-test-create"])

    assert "CREATE EXTENSION IF NOT EXISTS postgis" in recipe
    assert "pg_database" in recipe, "must check for the database before creating it"


# ------------------------------------------------------------ no silent success


def test_no_recipe_ignores_its_own_failures() -> None:
    # spec: ops-003 -- the first failure case. A leading `-` or a trailing
    # `|| true` makes make continue past a failed command, which is precisely
    # "a target that succeeds while the underlying compose command fails".
    offenders = [
        f"{target}: {line}"
        for target, lines in _recipes().items()
        for line in lines
        if line.startswith("-") or "|| true" in line or "; true" in line
    ]

    assert offenders == []


def test_no_target_needs_a_host_toolchain_beyond_docker() -> None:
    # spec: ops-003 -- what makes the demo reproducible on a machine that is
    # not the development one. backend/Makefile is the native equivalent and is
    # deliberately not merged with this file.
    offenders = [
        f"{target}: {line}"
        for target, lines in _recipes().items()
        for line in lines
        if any(tool in line for tool in HOST_TOOLCHAIN)
        and "$(COMPOSE)" not in line
        and "$(MAKE)" not in line
    ]

    assert offenders == []
