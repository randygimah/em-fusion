"""Mutation pass over ai-002, the template hypothesis generator.

A mutation pass asks whether the tests would notice a change, and this is
the item where that question is unusually load-bearing, because the
template generator is the thing the other arms are measured *against*. A
defect in a model arm shows up as a bad hypothesis a scorer can see. A
defect here shifts the baseline, and every comparison drawn against it
moves with it silently -- a generator that quietly cites one kind of
evidence too few makes the model arms look better by exactly that much.

Three families of site, and they fail in different directions.

**Silent weakening.** Truncating the uncertainties, dropping the standing
alternative, citing only the first two kinds. Each of these produces a
shorter, cleaner, still schema-valid hypothesis. None of them errors, and
the direction of the error is always toward a more confident-reading
account than the evidence supports -- which is exactly the failure this
whole layer exists to prevent.

**Silent widening.** Defaulting a missing confidence, accepting a number,
tolerating two verdict items and taking the first. These turn a refusal
into an answer, and the answer looks like every other answer.

**Order.** Sorting the citations, reversing the uncertainties, putting the
standing caveat first. Nothing is lost and nothing is invented; the
hypothesis simply stops being a function of the bundle alone. This project
has produced a result that differed between runs from an unordered
collection three times, so these sites are not hypothetical.
"""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/ai/template.py"
T = "tests/test_ai_template.py"
PY_BIN = os.environ.get("PY_BIN", str(ROOT / ".venv/bin/python"))

M = {
    # --- confidence is the rule's, not this generator's --------------------
    "confidence becomes a constant High": (
        "        return Confidence[word.upper()]",
        "        return Confidence.HIGH"),
    "the two vocabularies are joined by capitalisation": (
        "        return Confidence[word.upper()]",
        "        return Confidence(word.title())"),
    "a missing confidence defaults to Low": (
        "    if not isinstance(word, str):\n        raise TemplateError(",
        "    if not isinstance(word, str):\n        return Confidence.LOW\n"
        "    if False:\n        raise TemplateError("),
    "a missing confidence is read as the word 'low'": (
        '    word = verdict.details.get("confidence")',
        '    word = verdict.details.get("confidence", "low")'),
    "confidence is read off the first evidence item, not the verdict": (
        '    word = verdict.details.get("confidence")',
        '    word = bundle.evidence[0].details.get("confidence")'),

    # --- exactly one verdict, per evb-002's own rule -----------------------
    "a bundle with no verdict falls back to its first item": (
        "    if not found:\n        raise TemplateError(",
        "    if not found:\n        found = [bundle.evidence[0]]\n"
        "    if False:\n        raise TemplateError("),
    "two verdict items are tolerated and the first is taken": (
        "    if len(found) > 1:", "    if False:"),
    "the verdict is matched on the rule id instead of the finding type": (
        "        item for item in bundle.evidence "
        "if item.finding_type == bundle.anomaly_type",
        "        item for item in bundle.evidence if item.rule_id == bundle.rule_id"),

    # --- a citation stands for a KIND, identified by the pair --------------
    "citations are grouped on the rule id alone": (
        "        grouped.setdefault((item.rule_id, item.finding_type), "
        "[]).append(item)",
        "        grouped.setdefault((item.rule_id, item.rule_id), []).append(item)"),
    "citations are grouped on the finding type alone": (
        "        grouped.setdefault((item.rule_id, item.finding_type), "
        "[]).append(item)",
        "        grouped.setdefault((item.finding_type, item.finding_type), "
        "[]).append(item)"),
    "one citation per item rather than per kind": (
        "        grouped.setdefault((item.rule_id, item.finding_type), "
        "[]).append(item)",
        "        grouped[(item.rule_id, item.finding_type, id(item))] = [item]"),
    "citations are sorted alphabetically rather than left in bundle order": (
        "        for (rule_id, finding_type), items in grouped.items()",
        "        for (rule_id, finding_type), items in sorted(grouped.items())"),
    "only the first two kinds are cited": (
        "        for (rule_id, finding_type), items in grouped.items()",
        "        for (rule_id, finding_type), items in list(grouped.items())[:2]"),
    "a group of several is described as though it were one": (
        "    first = items[0]\n    if len(items) == 1:",
        "    first = items[0]\n    if True:"),
    "a group of several loses the count it stands for": (
        'f"{len(items)} findings of this kind across "',
        'f"findings of this kind across "'),

    # --- alternatives: what the system itself ruled out --------------------
    "superseded claims are dropped from the alternatives": (
        "        for claim in bundle.superseded\n    ]",
        "        for claim in ()\n    ]"),
    "a superseded claim loses the reason it was set aside": (
        'f"in favour of {claim.claimed_by}, because {claim.reason}. It is a "',
        'f"in favour of {claim.claimed_by}. It is a "'),
    "a superseded claim is also cited as supporting evidence": (
        "        supporting_evidence=_citations(bundle),",
        "        supporting_evidence=_citations(bundle)\n"
        "        + tuple(\n"
        "            Citation(rule_id=c.rule_id, finding_type=c.anomaly_type,\n"
        "                     statement=c.reason)\n"
        "            for c in bundle.superseded\n"
        "        ),"),
    "the standing alternative is dropped": (
        "    if standing is not None:\n        out.append(standing)",
        "    if standing is not None:\n        pass"),
    "both kinds of claim get the same standing alternative": (
        "    standing = _STANDING_ALTERNATIVE.get(bundle.anomaly_type)",
        "    standing = _STANDING_ALTERNATIVE[SENSOR_FAULT]"),
    "the outside-the-ruleset caveat is dropped": (
        "    out.append(_OUTSIDE_THE_RULES)", "    pass"),
    "the outside-the-ruleset caveat comes first instead of last": (
        "    out.append(_OUTSIDE_THE_RULES)", "    out.insert(0, _OUTSIDE_THE_RULES)"),

    # --- uncertainties, whole and in order ---------------------------------
    "the uncertainties are truncated to the first three": (
        "            u.statement for u in bundle.known_uncertainties",
        "            u.statement for u in bundle.known_uncertainties[:3]"),
    "the not-applicable absences are filtered out": (
        "            u.statement for u in bundle.known_uncertainties",
        "            u.statement for u in bundle.known_uncertainties "
        'if u.subject != "track"'),
    "the uncertainties arrive in reverse order": (
        "            u.statement for u in bundle.known_uncertainties",
        "            u.statement for u in reversed(bundle.known_uncertainties)"),
    "an uncertainty is reduced to the name of its kind": (
        "            u.statement for u in bundle.known_uncertainties",
        "            u.kind.value for u in bundle.known_uncertainties"),

    # --- the prose an analyst actually reads -------------------------------
    "the title drops the subject": (
        'return f"{claim[:1].upper()}{claim[1:]} at {bundle.subject}"',
        'return f"{claim[:1].upper()}{claim[1:]}"'),
    "the title becomes a constant": (
        'return f"{claim[:1].upper()}{claim[1:]} at {bundle.subject}"',
        'return "Anomaly detected"'),
    "the summary loses the end of the window": (
        'f"{_clock(ended)} UTC{channels}. The rule states: "',
        'f"UTC{channels}. The rule states: "'),
    "a source sentence already ending in a full stop gets a second one": (
        '    return text.rstrip(". ") + "."', '    return text + "."'),
    "the summary loses the window entirely": (
        "f\"{bundle.subject} between {started.strftime('%Y-%m-%d %H:%M:%S')} and \"",
        'f"{bundle.subject} "'),
    "every bundle gets the same recommended action": (
        "    template = _ACTION.get(bundle.anomaly_type, _GENERIC_ACTION)",
        "    template = _GENERIC_ACTION"),
    "the recommended action stops naming the subject": (
        "    action = template.format(subject=bundle.subject)",
        '    action = template.format(subject="the affected receivers")'),
    "an unmeasurable aircraft side reads like a clean negative": (
        '    if any(u.subject == "track" for u in bundle.known_uncertainties):',
        "    if False:"),

    # --- the schema is the gate, not a type annotation ---------------------
    "the hypothesis is built without validation": (
        "    return Hypothesis(", "    return Hypothesis.model_construct("),
}

#: Established by running the pass, not predicted. Every field this
#: generator produces is non-empty by construction -- a bundle cannot be
#: built with no evidence (`evb-001` refuses it), the alternatives always
#: carry the unconditional caveat, and every composed string embeds a
#: literal -- so on any bundle that can exist, validation has nothing to
#: reject and `model_construct` returns an equal object. The constructor is
#: kept rather than removed because that argument is about today's fields:
#: it stops holding the moment one of them becomes conditional, and the
#: failure would then be an unvalidated hypothesis in front of an analyst,
#: reported as though the schema had passed it.
EXPECTED_EQUIVALENT = {"the hypothesis is built without validation"}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        F.write_text(orig.replace(o, w, 1))
        # See measurements/README.md: CPython validates a cached .pyc on the
        # source's (mtime-in-whole-seconds, size), so two consecutive mutants
        # of the same length can run each other's bytecode.
        shutil.rmtree(F.parent / "__pycache__", ignore_errors=True)
        p = subprocess.run([PY_BIN, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        t = [l for l in p.stdout.splitlines()
             if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:62} {res[n]}", flush=True)
finally:
    F.write_text(orig)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
print(f"\n{killed} killed of {len(res) - len(invalid)} valid mutants")
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
expected = [n for n in survived if n in EXPECTED_EQUIVALENT]
if expected:
    print("SURVIVED, and equivalent -- see the note above:")
    for n in expected:
        print(f"  - {n}")
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
