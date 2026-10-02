"""When a run was examined by the detection pass. Spec: anom-015, api-012.

**The one fact the findings table cannot hold.** `0008` put the detector
settings on each finding, which answers *under what thresholds was this row
produced*. It cannot answer *was this run examined at all*, and the reason is
`db-008`'s own write semantics: findings are replaced per run per rule
**including at zero**, so a run examined and found clean leaves no rows, which
is byte-for-byte what a run nobody examined leaves. A pass pointed at the wrong
observations leaves the same. Three of those cases are failures and no property
of the table separates them -- `anom-008`'s argument, and the thing `api-012`
cannot serve honestly without a record here.

**Two columns and not one.** The policy sits beside the stamp as well as on the
findings, because a quiet run has *no findings to carry it*: a run scored under
thresholds nobody recorded is exactly the case `anom-008`'s measured bands were
taken under, and it is the case where the provenance matters most, zero being
the answer the control is checking. `eval-003`'s rule applies at this boundary
too -- a recorded setting that is not the one in force is worse than none,
because it looks like provenance.

**Nullable, on `db-007`'s argument rather than for `0008`'s reason.** This is
not a column with residue to accommodate; it is a column whose absence is the
informative state. `db-007` made `completed_at` nullable so that *not known to
have finished* covers both a run still going and a run that died, and refused a
three-valued status column for the same reason `app/scenario/guard.py` keeps the
batch bound in memory: a persisted flag is a claim no crash can retract. Here,
absence means *not known to have been scored*, which covers a run nothing ever
looked at and a pass that died before it finished -- and the pass stamps last,
after every write it makes, so the second really is the state the run is in.

A default would be the whole defect: `now()` would report the entire corpus as
examined the moment this migration ran.

Reversible. The downgrade drops both columns, losing the record that a pass ran
rather than corrupting it; re-running the pass is the recovery, which `db-008`'s
replace semantics already make safe.

Revision ID: 0009_detection_pass_stamp
Revises: 0008_detection_finding_policy
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0009_detection_pass_stamp"
down_revision = "0008_detection_finding_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenario_runs",
        sa.Column("detection_pass_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scenario_runs", sa.Column("detection_policy", JSONB, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("scenario_runs", "detection_policy")
    op.drop_column("scenario_runs", "detection_pass_at")
