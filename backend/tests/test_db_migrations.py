"""Migration configuration. Spec: db-001.

Deliberately needs no database. `alembic_config` resolves paths and reads a
committed ini file, so the parts of `db-001` that are about *locating* the
migrations are provable in the unit tier, and only the parts that are about
*applying* them need the live-database tier in `test_db_schema.py`.

That split is what keeps `app/db/migrations.py` fully measured on a machine
with no Docker, rather than sitting at 70 per cent behind a skip.
"""

from __future__ import annotations

import configparser

from alembic.script import ScriptDirectory

from app.db.migrations import ALEMBIC_INI, SCRIPT_LOCATION, alembic_config


def test_the_committed_ini_and_script_directory_exist() -> None:
    # spec: db-001
    assert ALEMBIC_INI.is_file()
    assert (SCRIPT_LOCATION / "env.py").is_file()


def test_script_location_is_absolute() -> None:
    # spec: db-001 -- Alembic resolves script_location relative to the working
    # directory unless told otherwise, and the backend is run from at least
    # three of them: backend/, the repository root, and /app in the container
    location = alembic_config().get_main_option("script_location")

    assert location is not None
    assert location == str(SCRIPT_LOCATION)
    assert SCRIPT_LOCATION.is_absolute()


def test_the_committed_ini_holds_no_connection_string() -> None:
    # spec: db-001, NFR-401 -- the URL comes from the environment. A DSN here
    # would be a credential in a committed file, and would also mean a stray
    # `alembic upgrade head` addressed a database nobody chose.
    parser = configparser.ConfigParser()
    parser.read(ALEMBIC_INI)

    assert parser.get("alembic", "sqlalchemy.url", fallback="").strip() == ""


def test_there_is_exactly_one_migration_head() -> None:
    # spec: db-001 -- two heads means two revisions claim the same parent, and
    # `upgrade head` then fails with an ambiguity rather than applying either.
    # It is introduced by writing a revision without checking the current head,
    # which is exactly the mistake hand-written revisions invite.
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1
