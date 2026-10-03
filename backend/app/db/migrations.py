"""Locating and running the Alembic migrations. Spec: db-001.

One place that knows where `alembic.ini` lives, so the test suite, a
`make migrate` target, and anything else all drive the same configuration
rather than three copies of a path. Alembic resolves `script_location`
relative to the current working directory unless told otherwise, and the
backend is run from at least three of them -- `backend/`, the repository
root, and `/app` inside the container -- so the path is made absolute here
rather than trusted to the caller's shell.

`sqlalchemy.url` is deliberately *not* baked in. `alembic_config` leaves it
as whatever `alembic.ini` holds and `env.py` falls back to `DATABASE_URL`;
tests override it to point at the disposable database instead. That is what
keeps a schema-dropping test from ever addressing the application's own
database by default.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

#: `backend/`, two levels up from `app/db/migrations.py`.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
SCRIPT_LOCATION = BACKEND_ROOT / "alembic"


def alembic_config() -> Config:
    """The project's Alembic configuration, with an absolute script location."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    return config


#: The database is at the revision this code was written against.
AT_HEAD = "at-head"
#: It is not, in any of the four ways that can happen. The one state that refuses.
DRIFTED = "drifted"
#: We could not find out. **Not** a refusal -- see `SchemaState`.
UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SchemaState:
    """Whether the database is at the revision the code expects. Spec: ops-005.

    **Three values and not two**, and the third is the whole of the design. An
    unreachable database is `UNKNOWN` and stays *healthy*: an outage is not a
    misconfiguration, and refusing on one would turn a degraded database into an
    unreachable service, which is the failure `api-001` was written to avoid and
    the reason this check is not a startup gate (`db-005` opens no connection at
    startup on purpose, and determining a revision needs one).

    `found` is `None` in two states and the pair disambiguates it: with
    `DRIFTED` it means *nobody has migrated this database*, with `UNKNOWN` it
    means *we could not look*. One is a deployment that has not finished and the
    other is an outage, which is the distinction the whole item is about.

    `expected` is `None` only when the migrations on disk do not have exactly one
    head, because then there is no single revision to be at.
    """

    status: str
    expected: str | None
    found: str | None
    detail: str

    @property
    def healthy(self) -> bool:
        """Whether the service should report itself serviceable."""
        return self.status != DRIFTED


def heads_on_disk(config: Config) -> tuple[str, ...]:
    """Every head in the migration graph, as the revision files declare it.

    The raw fact and no interpretation: zero heads, one, or several are three
    different conditions and `compare_schema` is where they are read. Takes its
    config so the two-head case is testable without a second migration tree in
    the repository.
    """
    return tuple(ScriptDirectory.from_config(config).get_heads())


@cache
def expected_revision() -> str | None:
    """The revision this code expects, or None when there is not exactly one.

    **Cached, because it cannot change without restarting the process**, and the
    health probe runs every five seconds. The database's own revision is
    deliberately *not* cached -- see `app/db/repository.py`'s `schema_state`.
    """
    heads = heads_on_disk(alembic_config())
    return heads[0] if len(heads) == 1 else None


def compare_schema(heads: Sequence[str], found: str | None) -> SchemaState:
    """Read a database's revision against the heads on disk. Spec: ops-005.

    Pure, and separated from the read for the usual reason: every branch here is
    a condition a real database takes minutes to arrange and this function takes
    none. The read is one line in the repository.

    **The expectation comes from the migrations and never from the database.**
    Taken out of `alembic_version` -- the table being checked -- this comparison
    would agree with itself on every database, which is a guard that cannot fail
    and therefore is not one.
    """
    if len(heads) != 1:
        return SchemaState(
            status=DRIFTED,
            expected=None,
            found=found,
            detail=(
                f"the migration graph has {len(heads)} heads, so there is no single "
                "revision to be at. Until that is resolved nothing can say whether "
                "this database is up to date."
            ),
        )
    expected = heads[0]
    if found == expected:
        return SchemaState(
            status=AT_HEAD,
            expected=expected,
            found=found,
            detail=f"the database is at {expected}, which is what this code expects.",
        )
    if found is None:
        return SchemaState(
            status=DRIFTED,
            expected=expected,
            found=None,
            detail=(
                f"this database has never been migrated: it names no revision, and "
                f"this code expects {expected}. Run `make migrate`."
            ),
        )
    return SchemaState(
        status=DRIFTED,
        expected=expected,
        found=found,
        detail=(
            f"this database is at {found} and this code expects {expected}. If it is "
            f"behind, run `make migrate`; if it is ahead, this code is older than the "
            f"schema and reading it may reference columns that no longer exist."
        ),
    )


def unreachable(why: str) -> SchemaState:
    """We could not find out, which is not a refusal. Spec: ops-005, api-001.

    A separate constructor rather than a branch in `compare_schema`, because that
    function is about comparing two revisions and this state has only one of them.
    """
    return SchemaState(
        status=UNKNOWN,
        expected=expected_revision(),
        found=None,
        detail=(
            f"the schema revision could not be read ({why}), so this says nothing "
            "about whether the database is up to date. Reported rather than refused: "
            "a database that is down is an outage and not a deployment mistake."
        ),
    )
