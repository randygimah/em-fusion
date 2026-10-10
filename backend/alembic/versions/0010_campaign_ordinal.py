"""Each stored hypothesis's position in its campaign. Spec: db-012.

**The fact the Hypotheses screen needs and the store did not hold.** The
screen shows the explanation the blind scoring used: the first generation the
hosted arm was asked for on each bundle (`eval-004`'s `SCORED_ORDINAL`). That
ordinal was written only in the committed campaign record. Row order is not a
substitute: measured on 2026-10-10, the earliest hosted row per bundle was the
scored one on none of twenty, because trial requests were stored first.

**Nullable, and null is informative.** A row written outside a campaign has no
position, and one stored before this column existed has none until the
committed record is copied in. A default of 1 would be the whole defect: it
would make every trial row look like a first generation.

**Unique per bundle, asked arm and position**, where a position is held. Two
rows claiming to be one campaign's first ask on one bundle cannot both be the
scored text, so the store refuses the second rather than leaving the reader to
pick.

Reversible. The downgrade drops the column and its index, losing positions the
campaign record can restore.

Revision ID: 0010_campaign_ordinal
Revises: 0009_detection_pass_stamp
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_campaign_ordinal"
down_revision = "0009_detection_pass_stamp"
branch_labels = None
depends_on = None

INDEX = "hypotheses_one_row_per_campaign_position"


def upgrade() -> None:
    op.add_column(
        "hypotheses",
        sa.Column(
            "campaign_ordinal",
            sa.Integer,
            sa.CheckConstraint(
                "campaign_ordinal >= 1", name="hypotheses_campaign_ordinal_positive"
            ),
            nullable=True,
        ),
    )
    op.create_index(
        INDEX,
        "hypotheses",
        ["bundle_id", "requested_generator", "campaign_ordinal"],
        unique=True,
        postgresql_where=sa.text("campaign_ordinal IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="hypotheses")
    op.drop_column("hypotheses", "campaign_ordinal")
