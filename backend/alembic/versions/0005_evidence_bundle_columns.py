"""Bring `evidence_bundles` up to what a bundle turned out to be. Spec: evb-002.

`0001` created the table with an anomaly type, two JSON blobs and a
timestamp. That was written before the detection layer existed, and every
other thing a bundle carries is missing from it: which run produced it,
which rule claimed it, what it is about, when, where, on which channels,
and which competing explanation was rejected. `evb-002` also needs the
resolved observation ids to survive, and those travel inside `evidence`
attached to the item that cited them -- see the item's own note on why a
join table was considered and not taken.

**Added rather than recreated.** `0001` has been applied to databases that
hold rows, so it is not edited; this is the same argument `0002` records.

`affected_area` is a **Point**, unlike `anomalies.affected_area`, which
`0001` made a Polygon. A bundle's area is its claim's centre, and a radio
anomaly is located at the receiver that reported it -- giving it an extent
would claim ground nothing was observed across, which is the argument
`FindingCluster` already makes for a group of one. The geometry column and
its index are written as raw SQL and created together, following `0001` and
`0003`: autogenerate does not understand PostGIS types, and a column whose
index is created elsewhere is a column whose index eventually is not.

Reversible, and the test asserts the column is present at head *before*
asserting it is gone after the downgrade -- otherwise that half passes
against any revision that never added it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_evidence_bundle_columns"
down_revision = "0004_observations_run_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_bundles",
        sa.Column(
            "scenario_run_id",
            sa.Integer,
            sa.ForeignKey("scenario_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    # The rule that claimed the event, carried from the finding through the
    # ladder to here (FR-402). It is what makes the bundle checkable.
    op.add_column("evidence_bundles", sa.Column("rule_id", sa.Text, nullable=False))
    # What the event is about: a receiver, or the receivers of a zone.
    op.add_column("evidence_bundles", sa.Column("subject", sa.Text, nullable=False))
    op.add_column(
        "evidence_bundles",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "evidence_bundles",
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
    )
    # The frequency axis, which is this builder's own -- nothing upstream
    # merges `anom-001`'s per-cell episodes across channels.
    op.add_column(
        "evidence_bundles", sa.Column("affected_channels", JSONB, nullable=False)
    )
    # Competing conclusions the ladder rejected. Outside `evidence` in the
    # object and outside it here, because co-occurrence read as concurrence
    # inverts the truth exactly.
    op.add_column(
        "evidence_bundles",
        sa.Column("superseded", JSONB, nullable=False, server_default="[]"),
    )
    op.create_check_constraint(
        "ck_evidence_bundles_window", "evidence_bundles", "ended_at >= started_at"
    )
    op.create_index(
        "ix_evidence_bundles_run", "evidence_bundles", ["scenario_run_id"]
    )

    op.execute(
        "ALTER TABLE evidence_bundles "
        "ADD COLUMN affected_area geometry(Point, 4326) NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_evidence_bundles_affected_area "
        "ON evidence_bundles USING GIST (affected_area)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_evidence_bundles_affected_area")
    op.drop_column("evidence_bundles", "affected_area")
    op.drop_index("ix_evidence_bundles_run", table_name="evidence_bundles")
    op.drop_constraint("ck_evidence_bundles_window", "evidence_bundles")
    for column in (
        "superseded",
        "affected_channels",
        "ended_at",
        "started_at",
        "subject",
        "rule_id",
        "scenario_run_id",
    ):
        op.drop_column("evidence_bundles", column)
