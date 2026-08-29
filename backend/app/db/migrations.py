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

from pathlib import Path

from alembic.config import Config

#: `backend/`, two levels up from `app/db/migrations.py`.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
SCRIPT_LOCATION = BACKEND_ROOT / "alembic"


def alembic_config() -> Config:
    """The project's Alembic configuration, with an absolute script location."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    return config
