"""The shape every hypothesis takes, whatever produced it. Spec: ai-001.

Three generators will produce explanations -- a deterministic template with
no model behind it, a hosted model, and a local one -- and all three hand
back this. That is what lets the screen render any of them without knowing
which ran, and what lets the evaluation compare them at all.

**This is a constraint on generation and not a description of it.** The
hosted arm is given `hypothesis_json_schema()` and will only emit
conforming output, so the guarantees here have to survive that derivation:
a translation that widened confidence to a free string would pass every
test written against the Python model and lose the guarantee at exactly the
boundary that relies on it. The derived schema is asserted on directly for
that reason.

**A supporting-evidence item is a structured citation, never a sentence.**
Prose cannot be resolved against a bundle, so a citation that is prose does
not make `ai-008` awkward -- it makes it impossible. And a citation names
*two* identifiers, because one does not identify: `anom-012` defines no
rule id of its own and borrows `anom-010`'s, so a rate-excess citation and
a discontinuity citation carry the same rule id while making different
claims, in every interference bundle the corpus produces.

**Nothing defaults.** A list that becomes empty because a generator omitted
it makes "weighed the alternatives and found none" and "never mentioned
alternatives" arrive identically -- `evb-001`'s typed-absence principle one
layer up. `alternative_explanations` carries a floor of one on top of that,
because a system built to stop a fluent model overclaiming must not accept
"there are no alternatives"; `evidence_against_or_uncertainty` deliberately
does not, because "nothing speaks against this" can be true where "nothing
else could explain this" essentially cannot.

Recorded as a limitation rather than solved: this stops a number in the
confidence *field* and cannot stop a generator writing "High (about 87%
sure)" into the summary. FR-715 is a rendering rule as well as a schema
rule, and the UI carries the other half.
"""

from __future__ import annotations

import copy
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Stripped, and empty after stripping is refused. A zero-length string
#: satisfies `str` and is not a title, and a single space satisfies a
#: length check and is not one either.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Confidence(str, Enum):
    """Exactly three, ordinal, never a number (FR-715, NFR-203).

    The spellings match the check constraint on the stored column, so a
    value that validates here cannot be refused by the database.
    """

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class _Strict(BaseModel):
    """Frozen, and unknown fields refused.

    Frozen because a hypothesis is a record of what a generator produced,
    and something adjustable after the grounding check ran is not that.
    Unknown fields refused because a model inventing `confidence_score`
    would otherwise smuggle a number into the object whose whole point is
    that it holds none.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class Citation(_Strict):
    """One thing the hypothesis rests on, named so it can be checked.

    `rule_id` and `finding_type` together are the identity -- see the
    module note on why the pair rather than the rule alone. `statement` is
    the generator's own words about that finding, which is what an analyst
    reads; it is not the thing `ai-008` resolves.
    """

    rule_id: NonBlank
    finding_type: NonBlank
    statement: NonBlank


class Hypothesis(_Strict):
    """One proposed explanation of one evidence bundle. FR-501."""

    hypothesis_title: NonBlank
    confidence: Confidence
    summary: NonBlank
    #: At least one. A hypothesis supported by nothing is the thing this
    #: whole layer exists to prevent.
    supporting_evidence: Annotated[tuple[Citation, ...], Field(min_length=1)]
    #: Required, and may be explicitly empty. See the module note.
    evidence_against_or_uncertainty: tuple[str, ...]
    #: At least one, and the floor is satisfiable rather than decorative: a
    #: fault bundle and an interference bundle are each other's competing
    #: conclusion, so the template generator can always name the one it did
    #: not pick.
    alternative_explanations: Annotated[tuple[str, ...], Field(min_length=1)]
    recommended_human_action: NonBlank


def hypothesis_json_schema() -> dict[str, Any]:
    """The derived schema a hosted generation is constrained by.

    Deep-copied on every call. It is pinned into a request and logged
    beside the result for reproducibility (`db-002`), and a caller that
    adjusted a shared dictionary for one request would change what every
    later request is generated under.
    """
    return copy.deepcopy(Hypothesis.model_json_schema())


__all__ = ["Citation", "Confidence", "Hypothesis", "hypothesis_json_schema"]
