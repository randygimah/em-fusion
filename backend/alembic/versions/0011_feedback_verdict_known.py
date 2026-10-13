"""The four verdicts, held by the store. Spec: api-005.

`analyst_feedback.verdict` was free text since `0001`. The endpoint validates
the verdict before writing, but anything else that writes (a script, a
backfill, a later route) would not, and a fifth spelling in the history would
leave the status no longer the mapping of the latest verdict. The set is the
backend's `Verdict` enum; this constraint repeats it so the store refuses
what the code would.

The table was empty when this was written (2026-10-13), and the verdicts the
tests insert are all members, so nothing existing is refused.

Reversible. The downgrade drops the constraint and loses nothing.

Revision ID: 0011_feedback_verdict_known
Revises: 0010_campaign_ordinal
"""

from __future__ import annotations

from alembic import op

revision = "0011_feedback_verdict_known"
down_revision = "0010_campaign_ordinal"
branch_labels = None
depends_on = None

CONSTRAINT = "analyst_feedback_verdict_known"
#: Spelled out rather than imported: a migration is a fixed point, and must
#: not change when the enum later does.
VERDICTS = ("confirm", "reject", "needs-more-evidence", "false-positive")


def upgrade() -> None:
    members = ", ".join(f"'{v}'" for v in VERDICTS)
    op.create_check_constraint(
        CONSTRAINT, "analyst_feedback", f"verdict IN ({members})"
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "analyst_feedback", type_="check")
