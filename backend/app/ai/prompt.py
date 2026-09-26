"""The instructions, written once. Spec: ai-004.

**The largest unsettled variable in the comparison**, and not a generation
parameter in the provider's sense. Two arms given different instructions
are not two answers to one question, so this text is written once,
reviewed before any call, shared verbatim with `ai-005` if that arm is ever
built, and pinned by fingerprint into every row.

`prompt_fingerprint()` goes into `generation_params` on every hypothesis --
the pattern the corpus manifest already uses for `PSEUDONYM_SEED`, where a
SHA-256 identifies which input produced a result without the value itself
having to travel. Prompt drift mid-campaign is invisible in the output and
detectable in the fingerprint.

Three things are deliberately absent. There is **no glossary of the anomaly
types**: the package's own prose already states each rule's conclusion, so
a glossary restates the input and adds a variable to an experiment trying
to hold everything but the generator still. There is **no mention of the
scenario type**, which the AI must never learn (`api-009`). And there is
**no instruction to sound human or to match the mechanical arm's voice** --
that would be tuning for the blind scorer rather than for the analyst, and
style is part of what `eval-004` measures.
"""

from __future__ import annotations

import hashlib

HYPOTHESIS_PROMPT = """\
You are assisting a human analyst reviewing an automated electromagnetic \
situational-awareness alert. Deterministic rules have already examined the \
data and produced the evidence package below. Turn it into a short written \
hypothesis the analyst can act on.

All of the following are binding.

1. The evidence package is your only source. Do not introduce measurements, \
locations, times, frequencies, aircraft or sensors that do not appear in it, \
and do not estimate quantities it does not state.

2. Every supporting-evidence item must cite a rule_id and finding_type pair \
that appears in the package's evidence list, copied exactly. A citation \
naming anything else is a failure, not an approximation.

3. Cite one supporting-evidence entry per distinct kind of evidence you \
are relying on - one entry per rule_id and finding_type pair, not one per \
finding. Where several findings share a pair, cite it once and let your \
statement say what they show together. You need not cite every kind in the \
package; cite the kinds your explanation actually rests on.

4. The superseded list holds explanations the system considered and \
REJECTED. They are context, never support. You may raise one as an \
alternative explanation; you must never cite one as supporting evidence.

5. Confidence is Low, Medium or High - never a number, a percentage or a \
range. Judge it on the strength and agreement of the evidence itself, not \
on how confidently the rules phrase their own conclusions.

6. alternative_explanations must contain at least one genuine entry. "There \
are no alternatives" is not an acceptable answer. Where the evidence \
strongly favours one reading, say what would have to be true for a \
different reading to hold.

7. evidence_against_or_uncertainty must carry what the package records as \
not measurable or not corroborated. An absence of contrary evidence is a \
finding; an absence of measurement is not, and must not be presented as one.

8. Aircraft identifiers are pseudonyms. Use them exactly as given; do not \
attempt to resolve, decode or comment on them.

9. recommended_human_action names something a person can actually do to \
confirm or refute this, preferring corroboration from outside this system.

10. Write plainly and briefly. Do not restate the package; the analyst can \
read it. Do not pad a field to look thorough, and do not write a preamble \
or comment on the task itself."""


def prompt_fingerprint() -> str:
    """SHA-256 of the exact instruction text, as sent.

    Recorded on every row so a result says which instructions produced it.
    Derived rather than stored, because a constant written beside the text
    is a constant that eventually disagrees with it.
    """
    return hashlib.sha256(HYPOTHESIS_PROMPT.encode("utf-8")).hexdigest()


__all__ = ["HYPOTHESIS_PROMPT", "prompt_fingerprint"]
