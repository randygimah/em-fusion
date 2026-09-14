"""Detection findings, and the run id `anomalies` never had. Spec: db-008.

`db-004` was picked up and had nothing to query. The `anomalies` table has
existed since `0001` and nothing has ever written to it or read it, so the
spatial query that justifies the spatial database had no rows to run over.
This revision creates the table the detectors' output actually lands in.

**A separate table rather than `anomalies`.** That table describes the
*reportable* kind of finding: it requires a `severity`, requires a Polygon
`affected_area`, and links to an evidence bundle. Neither rule built so far
produces any of the three. `anom-008`'s amendment made the missing severity
deliberate -- a quiet run holds around 138 track discontinuities, so these
are intermediate findings and never reach an analyst -- and `anom-001`'s
ninth decision made the missing area deliberate, because an area needs
corroboration from more than one source and inventing a radius would mean
modelling a coverage footprint the project has never measured. Forcing
findings into `anomalies` would mean three nullable columns and a polygon
that misstates what was observed.

**`location` is a Point, and it has a GiST index.** `0001` created one on
the `anomalies` geometry with a comment naming `db-004` as the reason; the
discontinuities `db-004` and `anom-004` query live here instead, so the
index follows them. Without it those queries still return correct answers,
by sequential scan -- they fail as a performance claim rather than a
correctness one, which is the kind of defect that survives every functional
test.

**`anomalies` gains `scenario_run_id`, NOT NULL and with no backfill.**
It has never carried one, so no anomaly could say which run produced it,
while every metric in `eval-002` is computed per run against that run's
recorded ground truth. The column is NOT NULL because the table is empty by
construction -- nothing has ever written to it. If that assumption is ever
false this migration fails loudly on the existing rows, which is the right
outcome: it would mean anomalies were being written by something nobody
recorded, and a silent backfill would invent a run id for each of them.

Revision ID: 0003_detection_findings
Revises: 0002_scenario_run_completion
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0003_detection_findings"
down_revision = "0002_scenario_run_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "detection_findings",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "scenario_run_id",
            sa.Integer,
            sa.ForeignKey("scenario_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The rule that produced it, carried on every row and into the
        # evidence bundle after that (FR-402). It is what makes a finding
        # checkable rather than merely stated.
        sa.Column("rule_id", sa.Text, nullable=False),
        sa.Column("finding_type", sa.Text, nullable=False),
        # What the finding concerns: a sensor and channel for an RF episode,
        # an aircraft for a track discontinuity. Text rather than two typed
        # columns, because a third detector's subject is neither of those and
        # would otherwise need a schema change.
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        # The readings that triggered it, by natural key. `evb-002` resolves
        # evidence against these.
        sa.Column("evidence_refs", JSONB, nullable=False),
        # Whatever is rule-specific: the RF severity and peak deviation, the
        # track gap's shape. Keeping it here is what lets one table hold
        # every rule's output without a column per rule.
        sa.Column("details", JSONB, nullable=False),
        sa.CheckConstraint("ended_at >= started_at", name="ck_findings_window"),
    )

    op.create_index(
        "ix_detection_findings_run_rule",
        "detection_findings",
        ["scenario_run_id", "rule_id"],
    )

    # Raw SQL for the geometry column, as `0001` does: autogenerate does not
    # understand PostGIS types, and the typed column plus its index are
    # created together so the two cannot drift apart.
    op.execute(
        "ALTER TABLE detection_findings "
        "ADD COLUMN location geometry(Point, 4326) NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_detection_findings_location "
        "ON detection_findings USING GIST (location)"
    )

    op.add_column(
        "anomalies",
        sa.Column(
            "scenario_run_id",
            sa.Integer,
            sa.ForeignKey("scenario_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("anomalies", "scenario_run_id")
    op.drop_table("detection_findings")
