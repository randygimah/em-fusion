"""The detector settings a finding was produced under. Spec: anom-015.

**Why a finding needs this and a run row does not.** A run records the seed and
the parameters it was generated from, which reproduce the *hours*. A finding is
produced by reading those hours through thirteen detector settings, and
`eval-003` records them beside the exported figures precisely because changing
one moves every catch rate, precision and latency on the same hours. Set the
radio threshold to 8 dB instead of 6 and the same run yields different findings,
with nothing on the row to say which reading it was.

Until now that did not matter, because nothing read a stored finding back:
`findings_for_run` has no caller outside the test suite, and every figure of
record re-derives the chain from the observations. `api-012` is what changes it
-- a screen reading stored findings would show figures taken under one setting
while the repository says another, and the disagreement would be undetectable
from either side.

**Nullable, and that is the honest shape rather than a weaker one.** The table
holds rows already -- residue from whichever measurement script ran last over
whichever runs it touched -- and they were written before any pass recorded a
policy. `NOT NULL` would need either a server default, which would invent
provenance that does not exist, or deleting those rows. A null here means
*written before `anom-015`*, which is true, and is the same three-valued-over-a-
nullable-column argument `0006` made for grounding: a hypothesis is written
before it is checked, so a two-valued flag makes *failed* and *never checked*
identical. Here it makes *produced under these settings* and *produced under
settings nobody recorded* identical, and the second is a real state this table
contains.

No default and no backfill, so `eval-001`'s distinction carries over: a finding
with no policy is **unprovenanced rather than wrong**, exactly as a run with no
batch record is, and a reader that treats the two the same reports an older
corpus as broken.

Reversible. The downgrade drops the column, losing the provenance rather than
corrupting it.

Revision ID: 0008_detection_finding_policy
Revises: 0007_hypothesis_requested_arm
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0008_detection_finding_policy"
down_revision = "0007_hypothesis_requested_arm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("detection_findings", sa.Column("policy", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("detection_findings", "policy")
