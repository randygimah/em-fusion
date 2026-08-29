"""Alembic runtime environment. Spec: db-001.

Online mode only. Offline mode emits SQL without a connection, and this
project's first revision *checks* for the PostGIS extension rather than
creating it -- a check that cannot run without a connection. Supporting a
mode in which the guard silently does nothing would be worse than not
supporting the mode.

`target_metadata` is None because autogenerate is disabled; there is no model
metadata to diff against, and there is deliberately not going to be.
"""

from __future__ import annotations

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.db.session import database_url

config = context.config

if not config.get_main_option("sqlalchemy.url", None):
    # No URL in the ini and none injected by a caller, so fall back to the
    # application's own source of truth -- which raises loudly when unset.
    config.set_main_option("sqlalchemy.url", database_url())

target_metadata = None


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


run_migrations_online()
