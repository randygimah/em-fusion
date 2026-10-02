"""Mutation pass over anom-016, the batch trigger and the settings of record.

**Almost every mutant here leaves a batch that generates, stores and reports
success.** That is the shape of the risk: the hours are the valuable thing and
they are written by code this item does not touch, so a trigger can be wrong in
every way available to it and the only symptom is a screen that says something
slightly false about runs that are perfectly fine.

Five surfaces.

**The two paths, which differ on purpose.** `python -m app.pipeline` built the 300
hours behind every figure this project quotes and must not score them; the
screen's path must. Both directions are mutated, because only one of them is a
guard -- a project with no detection at all satisfies the first.

**Which runs.** This batch's completed runs, never the store. A mutant that scores
every run of the batch, or that keeps scoring after a run fails, or that reports a
failed run as examined, leaves a report nobody reads closely and a stamp on a run
whose pass did not finish.

**What normal is measured over.** The quiet runs of the store, selected outside the
detection layer and crossing into it as ids. Mutants here are the quietest of the
lot: baselining over the staged runs, or over a run that died, or rebuilding the
baseline per run, all produce findings. The one that matters most is the metric --
a baseline built over SNR and thresholded as power is wrong in units, with both
halves individually valid.

**A failure that must not spread.** Nothing may raise out of the scoring stage: it
would reach `launch_batch`, which logs *scenario batch failed* -- false, the batch
having stored every hour it was asked for. Two mutants put the raise back.

**The eleven values.** The pin is a second statement of them and these mutants are
what say whether it is load-bearing: move a threshold, a box edge, a window, a
staleness clock, and the figures on screen stop being the figures in the thesis.

Five files, because the item is a seam: the settings, the pass's baseline builder,
the two repository readers, the trigger, and the measurement script whose copy it
replaces.

Runs in the container: half of these are only observable against a database, and a
host-only run would skip every database test and score their mutants as survivors
of a suite that never ran them.

**A mutant that cannot be imported tests nothing**, which the first run of this pass
found the hard way: the sentinel set the radio threshold to 99 dB, which violates
`ThresholdPolicy`'s own `threshold < medium_at < high_at` rule, so the module raised
on import and the suite reported three collection errors instead of one failing
test. That is the runtime twin of a mutant that does not parse -- killed by an error
rather than by a test -- and the harness is right to refuse to read it as a kill.
Two value mutants had the same defect and were replaced with single steps.

Run: `python measurements/mutation/mutate_anom016_batch_trigger.py` from
`backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SETTINGS = BACKEND / "app/detection/settings.py"
CHAIN = BACKEND / "app/detection/chain.py"
REPOSITORY = BACKEND / "app/db/repository.py"
TRIGGER = BACKEND / "app/scenario/batch.py"
PIPELINE = BACKEND / "app/pipeline.py"
SCRIPT = BACKEND / "measurements/corpus/detection_metrics.py"
FILES = (SETTINGS, CHAIN, REPOSITORY, TRIGGER, PIPELINE, SCRIPT)
TESTS = [
    "tests/test_anom_batch_trigger.py",
    "tests/test_anom_chain.py",
    "tests/test_api_scenario.py",
]

#: name -> (file, anchor, replacement)
M: dict[str, tuple[Path, str, str]] = {
    # --- the two paths -------------------------------------------------------
    "the corpus-building command reaches a detector": (
        PIPELINE,
        "from app.dal.models import DataMode",
        "from app.dal.models import DataMode\nfrom app.detection.chain import assess",
    ),
    "the batch generates and never scores": (
        TRIGGER,
        "    scoring = score_batch(summary, session_factory=sessions, layout=layout)\n"
        '    logger.info("scenario batch scored: %s", scoring.describe())',
        "    pass",
    ),
    "the batch scores before it generates": (
        TRIGGER,
        "    layout = load_layout()\n    summary = run_batch(",
        "    layout = load_layout()\n"
        "    score_batch(\n"
        "        BatchSummary(\n"
        '            base_seed=0, scenario_type="x", runs=(), seconds=0.0\n'
        "        ),\n"
        "        session_factory=sessions,\n"
        "        layout=layout,\n"
        "    )\n"
        "    summary = run_batch(",
    ),
    "the runs scored are not the runs just generated": (
        TRIGGER,
        "    scoring = score_batch(summary, session_factory=sessions, layout=layout)",
        "    scoring = score_batch(\n"
        '        BatchSummary(base_seed=0, scenario_type="x", runs=(), seconds=0.0),\n'
        "        session_factory=sessions,\n"
        "        layout=layout,\n"
        "    )",
    ),
    # --- which runs ----------------------------------------------------------
    "every run of the batch is examined, finished or not": (
        TRIGGER,
        "        if outcome.completed and outcome.run_id is not None",
        "        if outcome.run_id is not None",
    ),
    "a run the batch never opened is handed to the pass": (
        TRIGGER,
        "        if outcome.completed and outcome.run_id is not None",
        "        if outcome.completed",
    ),
    "the run is taken from the batch's claim rather than from its row": (
        TRIGGER,
        "            run = run_summary(session_factory, run_id)  "
        "# type: ignore[arg-type]\n"
        "            if run is None:\n"
        '                raise LookupError(f"run {run_id} is not in the store")',
        "            run = run_summary(session_factory, run_id)  "
        "# type: ignore[arg-type]\n"
        "            if False:\n"
        '                raise LookupError(f"run {run_id} is not in the store")',
    ),
    "a batch that completed nothing is reported as a refusal": (
        TRIGGER,
        "    if not requested:\n"
        "        return BatchScoring(requested=(), scored=(), failed=(), refused=None)",
        "    if not requested:\n"
        "        return BatchScoring(\n"
        '            requested=(), scored=(), failed=(), refused="nothing completed"\n'
        "        )",
    ),
    # --- what normal is measured over ----------------------------------------
    "normality is measured over the runs being scored": (
        TRIGGER,
        "            quiet_run_ids=quiet_run_ids(session_factory),  "
        "# type: ignore[arg-type]",
        "            quiet_run_ids=requested,",
    ),
    "the baseline is rebuilt for every run of the batch": (
        TRIGGER,
        "    scored: list[int] = []\n"
        "    failed: list[tuple[int, str]] = []\n"
        "    for run_id in requested:\n"
        "        try:",
        "    scored: list[int] = []\n"
        "    failed: list[tuple[int, str]] = []\n"
        "    for run_id in requested:\n"
        "        try:\n"
        "            normality = measure_normality(\n"
        "                session_factory,\n"
        "                quiet_run_ids=quiet_run_ids(session_factory),  "
        "# type: ignore[arg-type]\n"
        "                policies=policies,\n"
        "                window=window,\n"
        "            )",
    ),
    "the baseline's metric is hard-coded rather than taken from the policy": (
        CHAIN,
        "            policies.rf.metric,",
        # `__import__` because `RfMetric` is deliberately not a name this module
        # holds; the mutant has to reach it without a second anchor for the import.
        '            __import__(\n'
        '                "app.detection.baseline", fromlist=["RfMetric"]\n'
        "            ).RfMetric.POWER_DBM,",
    ),
    "an empty store is baselined against whatever it holds": (
        CHAIN,
        "    ids = tuple(quiet_run_ids)\n    if not ids:",
        "    ids = tuple(quiet_run_ids)\n    if False:",
    ),
    "a quiet run that did not finish is baselined over": (
        REPOSITORY,
        '                "SELECT id FROM scenario_runs WHERE scenario_type = :quiet "\n'
        '                "AND completed_at IS NOT NULL ORDER BY id"',
        '                "SELECT id FROM scenario_runs WHERE scenario_type = :quiet "\n'
        '                "ORDER BY id"',
    ),
    "the quiet runs come back in whatever order the store found them": (
        REPOSITORY,
        '                "AND completed_at IS NOT NULL ORDER BY id"',
        '                "AND completed_at IS NOT NULL"',
    ),
    "every run in the store counts as a quiet one": (
        REPOSITORY,
        '                "SELECT id FROM scenario_runs WHERE scenario_type = :quiet "\n'
        '                "AND completed_at IS NOT NULL ORDER BY id"\n'
        "            ),\n"
        '            {"quiet": ScenarioType.NORMAL_BASELINE.value},',
        '                "SELECT id FROM scenario_runs "\n'
        '                "WHERE completed_at IS NOT NULL ORDER BY id"\n'
        "            ),\n"
        "            {},",
    ),
    # --- a failure that must not spread --------------------------------------
    "a store with no quiet runs fails the batch": (
        TRIGGER,
        "        logger.warning("
        '"detection pass refused over %s runs: %s", len(requested), exc)\n'
        "        return BatchScoring(requested=requested, scored=(), "
        "failed=(), refused=str(exc))",
        "        raise",
    ),
    "one run failing stops the rest of the batch being examined": (
        TRIGGER,
        '            logger.exception("detection pass failed on run %s", run_id)\n'
        "            failed.append((run_id, str(exc)))",
        "            raise",
    ),
    "a run whose pass failed is reported as examined": (
        TRIGGER,
        "            failed.append((run_id, str(exc)))",
        "            scored.append(run_id)",
    ),
    # --- the run reader ------------------------------------------------------
    "the run summary reports whichever row the store returned first": (
        REPOSITORY,
        '                    "SELECT id, scenario_type, seed, started_at, '
        'completed_at "\n'
        '                    "FROM scenario_runs WHERE id = :run_id"',
        '                    "SELECT id, scenario_type, seed, started_at, '
        'completed_at "\n'
        '                    "FROM scenario_runs"',
    ),
    "a run that is not in the store raises instead of reporting its absence": (
        REPOSITORY,
        # The whole tail, because `latest_run` ends on the same line and an
        # anchor matching twice is scored INVALID rather than run.
        '                {"run_id": run_id},\n'
        "            )\n"
        "            .mappings()\n"
        "            .first()\n"
        "        )\n"
        "        return None if row is None else ScenarioRunSummary(**row)",
        '                {"run_id": run_id},\n'
        "            )\n"
        "            .mappings()\n"
        "            .first()\n"
        "        )\n"
        "        assert row is not None\n"
        "        return ScenarioRunSummary(**row)",
    ),
    # --- the label the rules may never see -----------------------------------
    "the pass reads the label for what was injected": (
        CHAIN,
        "    if run.completed_at is None:",
        "    _ = run.scenario_type\n    if run.completed_at is None:",
    ),
    # --- the eleven values ---------------------------------------------------
    "the radio threshold is loosened by two decibels": (
        SETTINGS,
        "    threshold=6.0,",
        "    threshold=8.0,",
    ),
    "the medium severity step moves by a decibel": (
        SETTINGS,
        "    medium_at=10.0,",
        "    medium_at=11.0,",
    ),
    "the high severity step moves by a decibel": (
        SETTINGS,
        "    high_at=15.0,",
        "    high_at=16.0,",
    ),
    "the box is a degree north of the corpus's own": (
        SETTINGS,
        "CORPUS_BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)",
        "CORPUS_BOX = BoundingBox(lat_min=50.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)",
    ),
    "the baseline looks back one hour rather than two": (
        SETTINGS,
        "BASELINE_WINDOW: timedelta = timedelta(hours=2)",
        "BASELINE_WINDOW: timedelta = timedelta(hours=1)",
    ),
    "contact counts as fresh for a different span": (
        SETTINGS,
        "    contact_fresh_within=timedelta(seconds=30),",
        "    contact_fresh_within=timedelta(seconds=20),",
    ),
    "the gap threshold is a minute and a half": (
        SETTINGS,
        "    threshold=timedelta(seconds=100),",
        "    threshold=timedelta(seconds=90),",
    ),
    "the measurement script declares the record for itself again": (
        SCRIPT,
        "POLICIES = POLICIES_OF_RECORD",
        "POLICIES = DetectorPolicies(rf=1, fault=2, gap=3, cluster=4, "
        "fusion=5, ladder=6)",
    ),
}

#: A mutant that cannot change behaviour, with the reason. `run_id is not None`
#: is a *type* guard and not a runtime one: `RunOutcome` defaults both fields and
#: `execute_run` sets them together, so no outcome the generator produces is
#: completed without an id. It is there because the comprehension is annotated
#: `tuple[int, ...]` and mypy has no other way to know. Removing it is therefore
#: equivalent, and a test written to kill it would have to construct an outcome
#: the system cannot produce.
EXPECTED_EQUIVALENT: dict[str, str] = {
    "a run the batch never opened is handed to the pass": (
        "the None check narrows a type rather than guarding a case: a completed "
        "RunOutcome always carries an id, so nothing the generator emits reaches it."
    ),
}

RAN = re.compile(r"(\d+) (?:passed|failed)")
ORIGINALS = {path: path.read_text() for path in FILES}

GUARD_FILE = Path(__file__).with_suffix(".in-progress.json")
if GUARD_FILE.exists():
    for name, text in json.loads(GUARD_FILE.read_text()).items():
        Path(name).write_text(text)
    GUARD_FILE.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The originals have been put back from the guard file. Check `git diff` "
        "is clean, then run again."
    )
GUARD_FILE.write_text(json.dumps({str(p): t for p, t in ORIGINALS.items()}))


def _restore() -> None:
    for path, text in ORIGINALS.items():
        path.write_text(text)


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        ["make", "test-backend-nobuild", f"PYTEST_ARGS={' '.join(TESTS)} -q --no-cov"],
        cwd=str(BACKEND.parent),
        capture_output=True,
        text=True,
    )
    tail = [
        line
        for line in p.stdout.splitlines()
        if "passed" in line or "failed" in line or "error" in line
    ]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(RAN.search(summary))


# --- the sentinel ---------------------------------------------------------
# A deliberately broken edit. If the suite stays green, edits are not reaching
# the tests and no score from this harness means anything.
# Not a value that breaks a policy's own validation: `threshold=99.0` violates
# `threshold < medium_at < high_at`, so the module raises on import and the suite
# reports collection errors rather than a failing test -- which this harness
# correctly refuses to read as a kill, and which aborted the first run of this
# pass. The baseline window has no such constraint and the pin catches it.
_from = "BASELINE_WINDOW: timedelta = timedelta(hours=2)"
assert ORIGINALS[SETTINGS].count(_from) == 1
SETTINGS.write_text(
    ORIGINALS[SETTINGS].replace(
        _from, "BASELINE_WINDOW: timedelta = timedelta(hours=3)", 1
    )
)
_code, _summary, _ran = _suite()
_restore()
if not _ran:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD_FILE.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        original = ORIGINALS[path]
        if original.count(o) != 1:
            res[n] = f"INVALID ({original.count(o)})"
            print(f"{n:70} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        # A mutant that does not parse tests nothing: it is killed by a syntax
        # error rather than by a test, which scores a gap as a pass.
        try:
            ast.parse(mutated)
        except SyntaxError as broken:
            res[n] = f"INVALID (does not parse: {broken.msg})"
            print(f"{n:70} {res[n]}", flush=True)
            continue
        # A mutant identical to the original tests nothing either, and reads as
        # a survivor -- the sixth hazard in measurements/README.md.
        if mutated == original:
            res[n] = "INVALID (identical to the original)"
            print(f"{n:70} {res[n]}", flush=True)
            continue
        path.write_text(mutated)
        code, summary, ran = _suite()
        res[n] = (
            f"INCONCLUSIVE -- {summary}"
            if not ran
            else ("KILLED   " if code else "SURVIVED ") + summary
        )
        print(f"{n:70} {res[n]}", flush=True)
        _restore()
finally:
    _restore()
    GUARD_FILE.unlink(missing_ok=True)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
print(f"\n{killed} killed of {len(res) - len(invalid) - len(unclear)} valid mutants")
if invalid:
    print(f"INVALID (anchor did not match once, or the mutant does not parse): {invalid}")
if unclear:
    print(f"INCONCLUSIVE (no test summary): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
for n, why in EXPECTED_EQUIVALENT.items():
    if n in survived:
        print(f"\nEQUIVALENT as expected: {n}\n  {why}")
