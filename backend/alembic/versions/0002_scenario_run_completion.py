"""Scenario run completion. Spec: db-007.

One nullable column, and every property of it is load-bearing.

**Nullable, with no server default and no backfill.** The column's meaning is
that absence is informative: a run whose `completed_at` is null is a run *not
known to have finished*. A default would stamp every row complete at the
moment it was created, which records an intention rather than an outcome, and
a backfill would stamp complete exactly the rows whose completion nobody
recorded -- the partial runs this revision exists to make findable.

**One column rather than a three-state status.** `running`, `failed` and
`crashed` read better and are worse, because a process killed outright cannot
record its own failure: a `failed` value would be right for a caught exception
and silently wrong for everything else. Null collapses the three into the one
thing a reader can actually assert.

**A second revision rather than an edit to `0001`.** The first revision has
been applied to databases that hold rows, and editing an applied revision
leaves those databases at a version that no longer describes them. Alembic's
whole value over ordered SQL files is that the version table stays true.

Revision ID: 0002_scenario_run_completion
Revises: 0001_core_schema
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_scenario_run_completion"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenario_runs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scenario_runs", "completed_at")
