"""Bring `hypotheses` up to what a hypothesis turned out to be. Spec: db-002.

`0001` created this table before the hypothesis had a settled shape, and
put four reproducibility columns on it that were exactly right -- its own
docstring explains why they had to exist from the first revision rather
than a later one: *a `raw_response` column added late, after an evaluation
campaign has run against a hosted model, is a campaign that has to be
repeated.*

What `0001` could not know is the field vocabulary `ai-001` later settled.
Comparing the table against it turns up four problems, and this revision
fixes all four while the table still holds **zero rows**, which it has
since it was created. Every one of these changes is free today and none of
them is free after a campaign.

**Three columns renamed rather than mapped.** `title`, `uncertainty` and
`alternatives` become `hypothesis_title`,
`evidence_against_or_uncertainty` and `alternative_explanations`. A
translation layer between two vocabularies is a permanent place for them to
drift, and the drift is silent: content stored under the wrong field's name
complains to nobody. With no rows to migrate, the rename is available
exactly once, and it is now.

**Two columns added.** `summary` is what an analyst reads first and
`recommended_human_action` is the entire point of decision support, and
neither had anywhere to go. `NOT NULL` with no server default is safe
precisely because the table is empty -- and if that assumption is ever
wrong, this fails loudly at migration time rather than quietly storing
blanks.

**`grounding_passed` becomes nullable.** Not a relaxation: a third state.
A hypothesis is written before `ai-008` examines it, so a two-valued flag
forces every new row to claim an outcome it does not have, and makes
*failed the check* and *was never checked* identical. That collapse is what
`evb-001`'s typed absences exist to prevent and this repository has now
recorded three times. `NULL` means not yet checked, and `app/db/hypotheses.py`
maps the three states to an enum so no consumer can write `if not passed`.

**`status` gains the check constraint its neighbours already had.**
`generator` and `confidence` are both constrained to their permitted
values; `status` accepted any text at all, while `FR-602` names exactly
five review states. The inconsistency was not deliberate.

Reversible. The downgrade restores the old names, drops the two added
columns and restores `NOT NULL` on `grounding_passed` -- which will fail if
any row has been written with no grounding verdict, correctly: that row
cannot be represented in the old schema, and silently inventing a verdict
for it is the one thing worse than refusing.

Revision ID: 0006_hypothesis_columns
Revises: 0005_evidence_bundle_columns
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_hypothesis_columns"
down_revision = "0005_evidence_bundle_columns"
branch_labels = None
depends_on = None

#: FR-602. A new hypothesis starts at `New`; the rest are `fbk-001`'s to
#: set. Spelled exactly as the requirement spells them, because a value
#: that differs by a capital is a value the constraint refuses at the
#: moment an analyst submits a verdict.
REVIEW_STATUSES = ("New", "Under review", "Confirmed", "Rejected", "Inconclusive")

#: `ai-001`'s names, which the column names now match exactly.
RENAMES = (
    ("title", "hypothesis_title"),
    ("uncertainty", "evidence_against_or_uncertainty"),
    ("alternatives", "alternative_explanations"),
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    for old, new in RENAMES:
        op.alter_column("hypotheses", old, new_column_name=new)

    op.add_column("hypotheses", sa.Column("summary", sa.Text, nullable=False))
    op.add_column(
        "hypotheses", sa.Column("recommended_human_action", sa.Text, nullable=False)
    )

    op.alter_column("hypotheses", "grounding_passed", nullable=True)

    op.create_check_constraint(
        "hypotheses_status_valid",
        "hypotheses",
        _in_list("status", REVIEW_STATUSES),
    )


def downgrade() -> None:
    op.drop_constraint("hypotheses_status_valid", "hypotheses", type_="check")
    op.alter_column("hypotheses", "grounding_passed", nullable=False)
    op.drop_column("hypotheses", "recommended_human_action")
    op.drop_column("hypotheses", "summary")
    for old, new in RENAMES:
        op.alter_column("hypotheses", new, new_column_name=old)
