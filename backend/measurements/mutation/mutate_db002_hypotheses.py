"""Mutation pass over db-002, hypothesis persistence.

A persistence layer fails quietly in a way a detector does not. A wrong
rule produces a wrong answer somebody eventually notices; a wrong write
produces a row that looks exactly like a right one and is discovered when
the thing it was supposed to make possible is attempted, which here is
months later and after a campaign has been paid for.

So nearly every site below **stores something plausible**. A renamed
column that still holds text. A parameter set serialised as a JSON null
rather than omitted. A grounding state that collapses two of its three
values. A write that replaces instead of appending. None of them raises,
and none of them is visible in a row.

Three families:

**Provenance.** The two guards that refuse a row whose generator does not
match what it carries, in both directions. `ai-003` already makes such a
result unconstructible, so these mutants are testing the second line
rather than the first -- which is the line that has to hold when a row
arrives some other way.

**The typed absence.** `grounding_passed` has three states over a nullable
column. Two of the mutants merge a pair of them, which is exactly the
collapse the enum exists to prevent and exactly what a `bool | None` would
have permitted.

**The schema itself.** The migration is mutated too, because a column that
is nullable when it should not be, or missing a constraint, is not
detectable from the Python at all.

**This harness drives `make test-backend-nobuild` from the repository
root.** Two things in that sentence are lessons rather than detail. From the
*root*, because two harnesses in this directory ran it from `backend/` where
the target does not exist, so `make` failed, so every mutant was scored
KILLED without a test having run. And `-nobuild`, because rebuilding the
image once per mutant is what exhausted memory and had the OOM killer stop
two passes mid-run, leaving a mutant on disk -- the backend service
bind-mounts `./backend`, so a source edit is already visible inside the
container and the rebuild was never doing anything. Run `make build-backend`
once before a pass. A non-zero exit code alone is not evidence a test
noticed anything, so the summary below also reports how many tests ran.

**Extended 2026-09-27** for the two additions `ai-012` forced, and the
guard file and sentinel were added at the same time -- this harness had
neither, which was recorded as owed. Two surfaces are new. The verdict
writer, where the interesting mutants are not "does it write" but "does it
write to the row it was given, does it write nothing else, and can it be
made to write the third state that would undo the whole point of a nullable
column". And the asked-for arm, where every mutant still stores a row: the
campaign runs both arms over one bundle, so a mutant that derives the
asked-for arm from the answering one produces a database in which a
fallback and the baseline are again indistinguishable, and nothing raises.
"""

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the repository root
BACKEND = ROOT / "backend"
MODULE = BACKEND / "app/db/hypotheses.py"
MIGRATION = BACKEND / "alembic/versions/0006_hypothesis_columns.py"
ASKED = BACKEND / "alembic/versions/0007_hypothesis_requested_arm.py"
BUNDLES = BACKEND / "app/db/bundles.py"
TESTS = "tests/test_db_hypotheses.py"

M = {
    # --- provenance, in both directions ------------------------------------
    "a model arm may omit its model id": (
        MODULE, '    if not (model_id or "").strip():', "    if False:"),
    "a model arm may omit its raw response": (
        MODULE, '    if not (raw_response or "").strip():', "    if False:"),
    "a template row may name a model": (
        MODULE,
        "        if model_id is not None or raw_response is not None:",
        "        if False:"),
    "the guard checks only the template direction": (
        MODULE, '    if not (model_id or "").strip():\n',
        "    if generator is None:\n"),
    "a blank model id counts as present": (
        MODULE, '    if not (model_id or "").strip():', "    if model_id is None:"),
    "the generator is not recorded from the result": (
        MODULE, '"generator": result.generator.value,',
        '"generator": "template",'),

    # --- what gets written -------------------------------------------------
    "the raw response is re-serialised rather than stored verbatim": (
        MODULE, '"raw_response": raw_response,',
        '"raw_response": (hypothesis.model_dump_json() if call else None),'),
    "an absent parameter set is stored as a JSON null": (
        MODULE,
        "                    \"generation_params\": (\n"
        "                        json.dumps(dict(call.parameters)) if call else None\n"
        "                    ),",
        "                    \"generation_params\": json.dumps(\n"
        "                        dict(call.parameters) if call else None\n"
        "                    ),"),
    "the summary is not stored": (
        MODULE, '"summary": hypothesis.summary,', '"summary": "",'),
    "the recommended action is not stored": (
        MODULE,
        '"recommended_human_action": hypothesis.recommended_human_action,',
        '"recommended_human_action": "",'),
    "the alternatives land in the uncertainty column": (
        MODULE,
        '                    "evidence_against": json.dumps(\n'
        "                        list(hypothesis.evidence_against_or_uncertainty)\n"
        "                    ),",
        '                    "evidence_against": json.dumps(\n'
        "                        list(hypothesis.alternative_explanations)\n"
        "                    ),"),
    "a new row starts under review rather than new": (
        MODULE, '"status": ReviewStatus.NEW.value,',
        '"status": ReviewStatus.UNDER_REVIEW.value,'),
    "a new row claims the grounding check passed": (
        MODULE, '"grounding_passed": GroundingStatus.NOT_CHECKED.to_stored(),',
        '"grounding_passed": True,'),
    "the write does not say which row it made": (
        MODULE, '") RETURNING id"', '")"'),

    # --- the typed absence, collapsed ---------------------------------------
    "not-checked is stored as failed": (
        MODULE,
        "        if self is GroundingStatus.NOT_CHECKED:\n            return None",
        "        if self is GroundingStatus.NOT_CHECKED:\n            return False"),
    "a stored null reads back as failed": (
        MODULE,
        "        if value is None:\n            return cls.NOT_CHECKED",
        "        if value is None:\n            return cls.FAILED"),
    "passed and failed are swapped": (
        MODULE, "        return cls.PASSED if value else cls.FAILED",
        "        return cls.FAILED if value else cls.PASSED"),

    # --- reading back -------------------------------------------------------
    "hypotheses come back in whatever order the heap gives": (
        MODULE, '"FROM hypotheses WHERE bundle_id = :bundle ORDER BY id"',
        '"FROM hypotheses WHERE bundle_id = :bundle"'),
    "another bundle's hypotheses are returned too": (
        MODULE, '"FROM hypotheses WHERE bundle_id = :bundle ORDER BY id"',
        '"FROM hypotheses ORDER BY id"'),

    # --- the schema, which Python cannot check ------------------------------
    "the two added columns are nullable": (
        MIGRATION, 'sa.Column("summary", sa.Text, nullable=False)',
        'sa.Column("summary", sa.Text, nullable=True)'),
    "the grounding column stays two-valued": (
        MIGRATION, '    op.alter_column("hypotheses", "grounding_passed", nullable=True)',
        "    pass"),
    "the review status keeps accepting any text": (
        MIGRATION,
        '    op.create_check_constraint(\n        "hypotheses_status_valid",',
        '    if False:\n        op.create_check_constraint(\n        "hypotheses_status_valid",'),
    "one column keeps its old name": (
        MIGRATION, '    ("uncertainty", "evidence_against_or_uncertainty"),', ""),
    "a review state the requirements name is left out": (
        MIGRATION, '"Inconclusive")', '"Inconclusive_typo")'),

    # --- the bundle identity this item had to expose ------------------------
    "stored bundles come back without their ids": (
        BUNDLES, '    return [(row["id"], _bundle(row)) for row in rows]',
        "    return [(0, _bundle(row)) for row in rows]"),
    "the new reader is not scoped to the run": (
        BUNDLES,
        '                    "FROM evidence_bundles "\n'
        '                    "WHERE scenario_run_id = :run "\n'
        '                    "ORDER BY started_at, subject, id"\n'
        "                ),\n"
        '                {"run": run_id},\n'
        "            )\n"
        "            .mappings()\n"
        "            .all()\n"
        "        )\n"
        '    return [(row["id"], _bundle(row)) for row in rows]',
        '                    "FROM evidence_bundles "\n'
        '                    "ORDER BY started_at, subject, id"\n'
        "                ),\n"
        '                {"run": run_id},\n'
        "            )\n"
        "            .mappings()\n"
        "            .all()\n"
        "        )\n"
        '    return [(row["id"], _bundle(row)) for row in rows]'),

    # --- the verdict, which had no writer at all -----------------------------
    "a failing verdict is recorded as passed": (
        MODULE,
        "    status = GroundingStatus.PASSED if report.passed else GroundingStatus.FAILED",
        "    status = GroundingStatus.PASSED"),
    "a failing verdict is recorded as never checked": (
        MODULE,
        "    status = GroundingStatus.PASSED if report.passed else GroundingStatus.FAILED",
        "    status = (\n"
        "        GroundingStatus.PASSED if report.passed else GroundingStatus.NOT_CHECKED\n"
        "    )"),
    "the two verdicts are swapped": (
        MODULE,
        "    status = GroundingStatus.PASSED if report.passed else GroundingStatus.FAILED",
        "    status = GroundingStatus.FAILED if report.passed else GroundingStatus.PASSED"),
    "the verdict is written to every row": (
        MODULE,
        '            text("UPDATE hypotheses SET grounding_passed = :passed WHERE id = :id"),\n'
        '            {"passed": status.to_stored(), "id": hypothesis_id},',
        '            text("UPDATE hypotheses SET grounding_passed = :passed"),\n'
        '            {"passed": status.to_stored()},'),
    "the verdict resets the analyst's review status": (
        MODULE,
        '            text("UPDATE hypotheses SET grounding_passed = :passed WHERE id = :id"),',
        '            text(\n'
        '                "UPDATE hypotheses SET grounding_passed = :passed, "\n'
        "                \"status = 'New' WHERE id = :id\"\n"
        "            ),"),
    "a verdict against no row is reported as written": (
        MODULE, "        if result.rowcount != 1:", "        if False:"),
    "a verdict against several rows is accepted": (
        MODULE, "        if result.rowcount != 1:", "        if result.rowcount > 1:"),

    # --- which arm was asked -------------------------------------------------
    "the asked-for arm is derived from the one that answered": (
        MODULE,
        '                    "requested_generator": requested_generator.value,',
        '                    "requested_generator": result.generator.value,'),
    "the asked-for arm is hard-coded to the template": (
        MODULE,
        '                    "requested_generator": requested_generator.value,',
        '                    "requested_generator": "template",'),
    "the asked-for arm is not read back": (
        MODULE,
        '        requested_generator=GeneratorKind(row["requested_generator"]),',
        "        requested_generator=GeneratorKind(row[\"generator\"]),"),
    "a fallback is never reported as one": (
        MODULE,
        "        return self.generator is not self.requested_generator",
        "        return False"),
    "the impossible direction is accepted": (
        MODULE,
        "    if (\n"
        "        requested_generator is GeneratorKind.TEMPLATE\n"
        "        and generator is not GeneratorKind.TEMPLATE\n"
        "    ):",
        "    if False:"),
    "every disagreement is refused, fallbacks included": (
        MODULE,
        "    if (\n"
        "        requested_generator is GeneratorKind.TEMPLATE\n"
        "        and generator is not GeneratorKind.TEMPLATE\n"
        "    ):",
        "    if requested_generator is not generator:"),
    "the direction guard is never reached from the writer": (
        MODULE,
        "    check_requested_arm(\n"
        "        generator=result.generator, requested_generator=requested_generator\n"
        "    )",
        "    pass"),

    # --- 0007, which Python cannot check ------------------------------------
    "the asked-for arm column is nullable": (
        ASKED,
        '        "hypotheses", sa.Column("requested_generator", sa.Text, nullable=False)',
        '        "hypotheses", sa.Column("requested_generator", sa.Text, nullable=True)'),
    "the asked-for arm accepts any text": (
        ASKED,
        "    quoted = \", \".join(f\"'{value}'\" for value in GENERATOR_VALUES)\n"
        "    op.create_check_constraint(",
        "    quoted = \", \".join(f\"'{value}'\" for value in GENERATOR_VALUES)\n"
        "    if quoted and False:\n"
        "        op.create_check_constraint("),
    "one generator kind is left out of the vocabulary": (
        ASKED,
        'GENERATOR_VALUES = ("template", "local", "hosted")',
        'GENERATOR_VALUES = ("template", "hosted")'),
    "the column is added and never dropped again": (
        ASKED, '    op.drop_column("hypotheses", "requested_generator")', "    pass"),
}

EXPECTED_EQUIVALENT: set[str] = set()

RAN = re.compile(r"(\d+) (?:passed|failed)")

originals = {path: path.read_text() for path in {p for p, _, _ in M.values()}}

# A crash between writing a mutant and restoring it leaves a mutated source
# on disk, where the next thing to read it is a measurement. The guard file
# holds the originals so a later run can put them back and refuse to score.
GUARD = Path(__file__).with_suffix(".in-progress.json")
if GUARD.exists():
    for name, text in json.loads(GUARD.read_text()).items():
        Path(name).write_text(text)
    GUARD.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The originals have been put back from the guard file. Check "
        "`git diff` is clean, then run again."
    )
GUARD.write_text(json.dumps({str(k): v for k, v in originals.items()}))


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        ["make", "test-backend-nobuild", f"PYTEST_ARGS={TESTS} -q --no-cov"],
        cwd=str(ROOT), capture_output=True, text=True, env=os.environ.copy())
    tail = [line for line in p.stdout.splitlines()
            if "passed" in line or "failed" in line or "error" in line]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(RAN.search(summary))


# --- the sentinel ---------------------------------------------------------
# A deliberately broken edit that must fail. Two harnesses in this directory
# once scored a perfect pass without running a test at all, so a score is
# only believable if a known-bad edit is shown to reach the suite first.
_from = '                    "generator": result.generator.value,'
_original = originals[MODULE]
assert _original.count(_from) == 1
MODULE.write_text(_original.replace(_from, '                    "generator": "local",', 1))
_code, _summary, _ran = _suite()
MODULE.write_text(_original)
if not _ran:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests and no score "
        "from this harness can be believed."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        orig = originals[path]
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:58} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        # A non-zero exit alone is not evidence a test noticed anything: a
        # harness that could not tell a failed test from a failed invocation
        # scored every mutant as killed. See the module docstring.
        code, summary, ran = _suite()
        if not ran:
            res[n] = f"INCONCLUSIVE -- {summary}"
        else:
            res[n] = ("KILLED   " if code else "SURVIVED ") + summary
        print(f"{n:58} {res[n]}", flush=True)
        path.write_text(orig)
finally:
    for path, text in originals.items():
        path.write_text(text)
    GUARD.unlink(missing_ok=True)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
print(f"\n{killed} killed of {len(res) - len(invalid) - len(unclear)} valid mutants")
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
if unclear:
    print(f"INCONCLUSIVE (no test summary -- the suite may not have run): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
