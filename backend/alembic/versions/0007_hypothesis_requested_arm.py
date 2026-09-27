"""Which arm was *asked*, not only which generator answered. Spec: db-002.

Found by building `ai-012`, the evaluation campaign that is this table's
first real caller, and it is the same class of defect as the late
`raw_response` that `0001`'s own docstring warns about: a column the rows
cannot do without, cheap now and impossible to backfill after a campaign.

**The two values differ exactly once, and it is the case that matters.**
`generator` records who wrote the text. When the model arm's answer fails
`ai-008` and `ai-007` falls back, the text is written by `ai-002` -- so the
row says `template`, which is true, and says nothing about the fact that a
model was asked first and could not be used. Since the campaign also runs
`ai-002` as the scored baseline over the *same* bundle, the two rows are
then byte-identical: the same deterministic generator over the same input.
Two rows differing in nothing, one of them the hosted arm's delivery.

Three consequences, none of which has a symptom. A fallback is invisible in
the data, so the fallback rate is a number with no rows behind it.
`eval-005`'s per-arm figures are ambiguous at precisely the rows that carry
the most weight. And `ai-010` -- a hypothesis produced by either fallback
path must be visibly distinguishable from a primary-arm one, or the analyst
cannot tell the AI layer has degraded -- is *unbuildable* on this schema
rather than merely unbuilt.

**`generator != requested_generator` is the definition of a fallback**, not
a state to refuse. Both fallbacks run in that direction: `ai-007` goes
model-to-template and `ai-006` goes hosted-to-local. The one nonsensical
combination -- the template named as the arm that was asked while a model
answered -- is refused at the repository boundary, where the pair is known,
following the split this table already uses: the vocabulary is constrained
here, the semantics in `app/db/hypotheses.py`.

`NOT NULL` with no server default, and both halves are deliberate. The
table still holds zero rows -- nothing in `app/` has ever written one --
which is the same free-today-and-never-again window `0006`'s renames used,
and this is the second and last use of it. A server default would be worse
than a nullable column: it would supply `generator`'s own value, which is
correct on every row except the fallback ones, and those are the only rows
this column exists for. If the empty-table assumption is ever wrong this
fails loudly at migration time, which is the intent.

Reversible. The downgrade drops the column and its constraint, which loses
the distinction rather than corrupting it.

Revision ID: 0007_hypothesis_requested_arm
Revises: 0006_hypothesis_columns
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_hypothesis_requested_arm"
down_revision = "0006_hypothesis_columns"
branch_labels = None
depends_on = None

#: The same three values `generator` has carried since `0001`, spelled the
#: same way. They are one vocabulary read two ways -- who was asked and who
#: answered -- and a second list that drifted by a letter would refuse a
#: row at the moment a campaign ran.
GENERATOR_VALUES = ("template", "local", "hosted")


def upgrade() -> None:
    op.add_column(
        "hypotheses", sa.Column("requested_generator", sa.Text, nullable=False)
    )
    quoted = ", ".join(f"'{value}'" for value in GENERATOR_VALUES)
    op.create_check_constraint(
        "hypotheses_requested_generator_valid",
        "hypotheses",
        f"requested_generator IN ({quoted})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "hypotheses_requested_generator_valid", "hypotheses", type_="check"
    )
    op.drop_column("hypotheses", "requested_generator")
