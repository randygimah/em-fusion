"""Mutation pass over evb-002, evidence traceability.

The risk this pass exists for is specific and it is not malformation. A
broken resolver produces a **well-formed bundle that cites the wrong rows**,
or one that certifies citations it never actually checked. Neither is
visible to a shape assertion, and the second is worse than no check at all:
a traceability check that passes by default tells `ai-008` the citations
were verified when they were not.

So the sites below are almost all *scoping and refusal* rather than
happy-path arithmetic. A resolver that drops the run filter still returns
one row per citation on a single-run database and is wrong on all 300. A
resolver that accepts a coordinate matching two rows is wrong only when the
corpus stops being unique, which is exactly when it matters. A shape check
written as a subset rather than an exact match accepts a ref whose keys have
drifted. `evb-001`'s pass learned the same lesson from the other end -- 10
of its 12 genuine survivors were scoping rules -- so the suite was written
with that in mind and this pass is the check on whether that worked.

Three sites live outside the resolver, in the rule and the finding, because
the defect this item found lives there: a citation that names the window
instead of the reports the rule read. Those two mutants restore the original
bug exactly, and a suite that does not kill them has not fixed anything.

**This harness mutates four files**, unlike the single-file passes beside
it, and each site names the tests that ought to notice -- running every
suite for every mutant would take twenty minutes to learn nothing extra.
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
PY_BIN = os.environ.get("PY_BIN", str(ROOT / ".venv/bin/python"))

BUNDLES = "app/db/bundles.py"
BUILDER = "app/detection/bundle.py"
TRACK = "app/detection/track_gap.py"
FINDINGS = "app/detection/findings.py"

TRACE = "tests/test_evb_traceability.py"
BUILT = "tests/test_evb_bundle.py"
GAPS = "tests/test_anom_track_gap.py"
STORED = "tests/test_db_findings.py"

#: name -> (file, old, new, tests)
M = {
  # --- exactly one row, and both ways of getting that wrong --------------
  "a citation matching nothing is accepted": (
      BUNDLES, "            if len(matched) != 1:", "            if len(matched) > 1:",
      [TRACE]),
  "a citation matching two rows is accepted": (
      BUNDLES, "            if len(matched) != 1:", "            if len(matched) < 1:",
      [TRACE]),
  "the first matching row is taken when several match": (
      BUNDLES, "            if len(matched) != 1:", "            if not matched:",
      [TRACE]),

  # --- scoped to the run, which is where the uniqueness was measured -----
  "the rf query is not scoped to the run": (
      BUNDLES,
      "            \"WHERE scenario_run_id = :run AND observation_type = 'rf' \"",
      "            \"WHERE :run IS NOT NULL AND observation_type = 'rf' \"",
      [TRACE]),
  "the track query is not scoped to the run": (
      BUNDLES,
      "            \"WHERE scenario_run_id = :run AND observation_type = 'track' \"",
      "            \"WHERE :run IS NOT NULL AND observation_type = 'track' \"",
      [TRACE]),
  "the rf query does not filter on observation type": (
      BUNDLES,
      "            \"WHERE scenario_run_id = :run AND observation_type = 'rf' \"",
      "            \"WHERE scenario_run_id = :run AND 'rf' IS NOT NULL \"",
      [TRACE]),
  "the read is not scoped to the run": (
      BUNDLES, "                    \"WHERE scenario_run_id = :run \"",
      "                    \"WHERE :run IS NOT NULL \"", [TRACE]),
  "the replace is not scoped to the run": (
      BUNDLES,
      "            text(\"DELETE FROM evidence_bundles WHERE scenario_run_id = :run\"),",
      "            text(\"DELETE FROM evidence_bundles WHERE :run IS NOT NULL\"),",
      [TRACE]),

  # --- the coordinate shapes are a closed set, matched exactly -----------
  "the rf shape is matched as a subset rather than exactly": (
      BUNDLES, "            if keys == RF_REF_KEYS:", "            if keys >= RF_REF_KEYS:",
      [TRACE]),
  "the track shape is matched on one key": (
      BUNDLES, "            elif keys == TRACK_REF_KEYS:",
      "            elif \"aircraft_id\" in keys:", [TRACE]),
  "an unknown shape is skipped rather than refused": (
      BUNDLES, "            else:\n                raise ResolutionError(",
      "            elif False:\n                raise ResolutionError(", [TRACE]),
  "the track shape is read as spelling its time `timestamp`": (
      BUNDLES, "TRACK_REF_KEYS = frozenset({\"aircraft_id\", \"at\"})",
      "TRACK_REF_KEYS = frozenset({\"aircraft_id\", \"timestamp\"})", [TRACE]),

  # --- a judgement is not looked up, and is not exempt by accident -------
  "a bundle of judgements still opens a transaction": (
      BUNDLES, "    if rf or track:", "    if True:", [TRACE]),
  "judgements are queried for rows they cannot have": (
      BUNDLES, "        if item.grounding is Grounding.DERIVED:\n            # A judgement",
      "        if False:\n            # A judgement", [TRACE]),

  # --- the ids answer the citations, in order ----------------------------
  "resolved ids are sorted rather than kept in citation order": (
      BUNDLES, "        resolved.append(replace(item, observation_ids=tuple(ids)))",
      "        resolved.append(replace(item, observation_ids=tuple(sorted(ids))))",
      [TRACE]),
  "resolved ids are not persisted": (
      BUNDLES, "        \"observation_ids\": list(item.observation_ids),",
      "        \"observation_ids\": [],", [TRACE]),
  "the grounding is not persisted": (
      BUNDLES, "        \"grounding\": item.grounding.value,",
      "        \"grounding\": Grounding.DERIVED.value,", [TRACE]),
  "longitude and latitude are transposed": (
      BUNDLES, "    return f\"SRID={SRID};POINT({location.lon} {location.lat})\"",
      "    return f\"SRID={SRID};POINT({location.lat} {location.lon})\"", [TRACE]),

  # --- the run is the unit of the write ----------------------------------
  "a bundle belonging to another run is written anyway": (
      BUNDLES, "        if bundle.scenario_run_id != scenario_run_id:", "        if False:",
      [TRACE]),
  "the replace happens before resolution": (
      BUNDLES,
      "    resolved = resolve_bundles(session_factory, bundles)\n"
      "    rows = [_row(bundle) for bundle in resolved]\n"
      "\n"
      "    with session_factory.begin() as session:\n"
      "        session.execute(\n"
      "            text(\"DELETE FROM evidence_bundles WHERE scenario_run_id = :run\"),\n"
      "            {\"run\": scenario_run_id},\n"
      "        )",
      "    with session_factory.begin() as session:\n"
      "        session.execute(\n"
      "            text(\"DELETE FROM evidence_bundles WHERE scenario_run_id = :run\"),\n"
      "            {\"run\": scenario_run_id},\n"
      "        )\n"
      "    resolved = resolve_bundles(session_factory, bundles)\n"
      "    rows = [_row(bundle) for bundle in resolved]\n"
      "\n"
      "    with session_factory.begin() as session:",
      [TRACE]),
  "an empty set of bundles leaves the old ones standing": (
      BUNDLES, "        if rows:\n            session.execute(",
      "        if True:\n            session.execute(", [TRACE]),

  # --- the declaration cannot lie, in either direction -------------------
  "an observation claim citing nothing is accepted": (
      BUILDER, "        if self.grounding is Grounding.OBSERVED and not self.refs:",
      "        if False:", [TRACE, BUILT]),
  "a judgement citing observations is accepted": (
      BUILDER, "        if self.grounding is Grounding.DERIVED and self.refs:",
      "        if False:", [TRACE, BUILT]),
  "episodes are declared judgements": (
      BUILDER, "            grounding=Grounding.OBSERVED,\n            data_mode=DataMode.SYNTHETIC,",
      "            grounding=Grounding.DERIVED,\n            data_mode=DataMode.SYNTHETIC,",
      [TRACE, BUILT]),
  "track findings are declared judgements": (
      BUILDER, "            grounding=Grounding.OBSERVED,\n            data_mode=DataMode.REPLAYED,",
      "            grounding=Grounding.DERIVED,\n            data_mode=DataMode.REPLAYED,",
      [TRACE, BUILT]),

  # --- the citation is what was read, not what was concluded -------------
  # These two restore the original defect exactly: 91 of 1,021 real
  # citations at an instant nothing was recorded at.
  "the frozen finding reports the reconstructed start as observed": (
      TRACK, "        observed_at=(first.timestamp, episode[-1].timestamp),",
      "        observed_at=(first.timestamp - first.position_staleness,\n"
      "                     episode[-1].timestamp),", [TRACE, GAPS]),
  "the refs cite the window start again": (
      FINDINGS, "\"at\": gap.observed_at[0].isoformat()},",
      "\"at\": gap.started_at.isoformat()},", [TRACE, GAPS, STORED]),
  "the not-heard finding reports its reports in the wrong order": (
      TRACK, "                observed_at=(before.timestamp, after.timestamp),",
      "                observed_at=(after.timestamp, before.timestamp),",
      [TRACE, GAPS]),
  # Recorded as EXPECTED-EQUIVALENT and kept deliberately: both builders set
  # `observed_at[1]` to the same value as `ended_at`, so nothing can tell
  # these apart. A survivor here is not a gap, and saying so in advance is
  # what stops the score being read as 27 of 28 by someone counting rows.
  "the refs cite the window end (equivalent)": (
      FINDINGS, "\"at\": gap.observed_at[1].isoformat()},",
      "\"at\": gap.ended_at.isoformat()},", [TRACE, GAPS, STORED]),
}

EXPECTED_EQUIVALENT = {
    "the refs cite the window end (equivalent)",
    # Established by the first pass rather than predicted. Removing the
    # first loop's skip lets a judgement reach the ref loop -- where it
    # iterates an empty tuple, because `EvidenceItem` refuses a DERIVED item
    # that carries refs. So the two guards make each other redundant, and
    # this mutant is equivalent *only while the constructor holds*: delete
    # that check and this becomes a live defect with no test on it. Kept in
    # the list for exactly that reason.
    "judgements are queried for rows they cannot have",
}

originals = {name: (ROOT / name).read_text()
             for name in {site[0] for site in M.values()}}
res = {}
try:
    for n, (filename, o, w, tests) in M.items():
        path = ROOT / filename
        orig = originals[filename]
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:58} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        # **Clear the bytecode cache, every time.** CPython validates a
        # `.pyc` on the source's (mtime-in-whole-seconds, size), and
        # consecutive mutants land in the same second -- so two that change
        # the file by the same number of bytes are indistinguishable to that
        # check and the second silently runs the first's bytecode. It scored
        # two genuinely-killed evb-001 mutants as SURVIVED, and the error has
        # no preferred direction: it can overstate a score just as easily.
        shutil.rmtree(path.parent / "__pycache__", ignore_errors=True)
        p = subprocess.run([PY_BIN, "-m", "pytest", *tests, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        t = [l for l in p.stdout.splitlines()
             if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:58} {res[n]}", flush=True)
        path.write_text(orig)
finally:
    for name, text in originals.items():
        (ROOT / name).write_text(text)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
valid = len(res) - len(invalid)
print(f"\n{killed} killed of {valid} valid mutants")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
expected = [n for n in survived if n in EXPECTED_EQUIVALENT]
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
if expected:
    print("SURVIVED, and declared equivalent before the run:")
    for n in expected:
        print(f"  - {n}")
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
