"""Index observations by the run that produced them. Spec: db-010.

`0001` gave `observations` a primary key and a GiST index on `location`, and
nothing else. `scenario_run_id` -- the column nearly every query in the
project filters on -- had nothing behind it, and it is also a foreign key
declared `ON DELETE CASCADE`, so deleting a run had to scan the whole table
to find its children.

**Found by measurement, not by review.** At 20.7 million rows in 12 GB, a
single pass of the detection measurements over the corpus was performing
three hundred sequential scans of the entire table, because each of those
scripts asks for one run's observations at a time. That is the difference
between a measurement taking seconds and taking half an hour, and it had
been quietly true since `0001`.

**An index changes no data and no answer**, only cost. That is what makes it
safe to add after figures have been measured: nothing recorded before this
revision is invalidated by it, which is emphatically not true of the other
changes landing around it. It is also why the defect survived every
functional test -- an unindexed column returns correct results by sequential
scan, and correctness is all the suite was asking about.

Reversible, because an index is exactly the kind of change that should drop
without touching a row.
"""

from alembic import op

revision = "0004_observations_run_index"
down_revision = "0003_detection_findings"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_observations_scenario_run_id"


def upgrade() -> None:
    op.create_index(INDEX_NAME, "observations", ["scenario_run_id"])


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="observations")
