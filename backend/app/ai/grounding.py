"""The automated grounding check. Spec: ai-008.

The load-bearing safeguard, and the one thing standing between a fluent
model and an analyst. `ai-004`'s constrained decoding guarantees a hosted
answer's **shape** -- every field present, confidence one of three words,
nothing invented in the object's structure -- and guarantees exactly
nothing about whether the things named *inside* it exist. A perfectly
formed hypothesis citing a rule that was never run is the failure this
whole layer was built around.

It is tractable only because of `evb-001`. The model receives one bundle
and nothing else, so "does this claim refer to something real" is a set
membership test against a closed list of a few dozen items, rather than an
unanswerable question about 20.7M observations.

**The identity is the pair, never the rule alone.** `anom-012` defines no
rule id of its own and borrows `anom-010`'s, so a rate excess and a track
discontinuity are indistinguishable by rule id while making different
claims -- in every interference bundle the corpus produces. `ai-001` made a
citation carry both identifiers for this module's sake; resolving only one
of them would throw that away at the point of use.

**The interesting half is the compartment.** A bundle carries rejected
competing claims in `superseded`, outside the evidence list, deliberately:
it is what lets a model write an honest alternative instead of pretending
none existed. That honesty creates the hole this module is amended for. A
check asking "does this identifier appear anywhere in the bundle" would
wave through a hypothesis citing one of those **as support** -- reading two
rules' disagreement as two rules' agreement, which inverts the truth
exactly and certifies the error the safeguard exists to catch. So there are
three verdicts, and `SUPERSEDED` never folds into `UNKNOWN`: an invented
identifier is a model hallucinating a name, while a superseded citation is
a model misreading the bundle it was handed, and the second is the more
alarming.

**Only the evidence list is citable.** Not the bundle's own top-level rule
id, which is metadata about the claim rather than an item of evidence --
citing the claim as support for itself is circular. And where a pair
somehow sits in both compartments the evidence wins, the sharper verdict
being reached only when the pair is genuinely absent from the evidence.

**Matching is exact, and near misses are recorded rather than forgiven.**
Normalising case or spacing would silently repair model output and
understate a catch rate `eval-005` reports as a *result*. But a bare count
says nothing: "14 catches" and "14 catches, 11 of them one rule's findings
mistaken for another's" are different findings, and only the second is
actionable. So a refused citation carries why it nearly matched, without
that ever softening the verdict.

**What this does not check.** The `statement` beside a citation is prose
and is not resolved. A model can name a real finding and say something
false about it, and this will pass it. That is `eval-004`'s scoring and no
part of a mechanical check -- recorded here as a property of the item
rather than left for an examiner to find. Nor does anything tie a
hypothesis to the bundle it was generated from: handed the wrong bundle
this reports a flood of unknown citations, which is the caller's error and
not a state this module can detect.

**`ai-002` is the oracle, so this must not share its fault.** A template
hypothesis is grounded by construction, which makes anything flagged on one
a defect *here* -- an unusually cheap validation, and the reason `ai-008`
sits late in the build order. It holds only while the two derive the
citation key independently: both group on the `(rule_id, finding_type)`
pair, and a shared derivation would make a defect in that key invisible,
the template emitting wrongly-keyed citations and this resolving
wrongly-keyed citations in perfect agreement. The independence is asserted
by walking the import graph, following `ai-007`.

**The arm is declared, never inferred.** A `Hypothesis` carries no record
of what produced it, so a per-arm catch rate is only possible if the arm is
stated where the check is wired in -- the argument `ai-009` settled for a
refused call, which has no result to read an arm off either. And a rate
over zero checks is `None` rather than 0.0: *never caught anything* and
*never ran* must not arrive identically, or the write-up sentence "the
check flagged nothing on the template arm" becomes true-looking in exactly
the case where that arm was never put through it.

Nothing here knows which arm is *expected* to pass. Encoding that the
template cannot be ungrounded would make the check's answer depend on who
it was asked about, which is the one property an instrument must not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.ai.hypothesis import Hypothesis
from app.ai.service import GenerationRefused, GeneratorKind
from app.detection.bundle import EvidenceBundle


class CitationVerdict(str, Enum):
    """What one citation turned out to be. Three, and the third is the point."""

    #: Names a `(rule_id, finding_type)` pair the bundle's evidence carries.
    GROUNDED = "grounded"
    #: Names nothing the bundle carries, in either compartment.
    UNKNOWN = "unknown"
    #: Names a claim `anom-013` rejected, cited in support. Kept apart from
    #: UNKNOWN because it is a different failure and the worse one.
    SUPERSEDED = "superseded"


class NearMiss(str, Enum):
    """Why a refused citation nearly resolved. Never a mitigation."""

    #: Differs from something the bundle carries only in case or spacing.
    #: Checked before the other, because it is the more specific reading:
    #: a rule with several finding types cited with one of them
    #: miscapitalised satisfies both, and reporting that as a rule
    #: confusion would invert what the measurement says.
    CASE_OR_SPACING = "case_or_spacing"
    #: The rule id is in the bundle, under one or more other finding types.
    #: The confusion `ai-001`'s two-identifier citation exists to catch.
    RULE_ID_UNDER_ANOTHER_TYPE = "rule_id_under_another_type"


@dataclass(frozen=True, slots=True)
class CitationFinding:
    """The determination for one citation, in the hypothesis's own order."""

    #: One-based, and it is a position rather than an index because it is
    #: printed: "citation 2" points an analyst at the second thing they
    #: read, not at the third.
    position: int
    rule_id: str
    finding_type: str
    verdict: CitationVerdict
    near_miss: NearMiss | None = None
    #: Empty on a grounded citation. A detail on every finding would make
    #: the failing ones unfindable by eye in a log.
    detail: str = ""

    @property
    def grounded(self) -> bool:
        return self.verdict is CitationVerdict.GROUNDED


@dataclass(frozen=True, slots=True)
class GroundingReport:
    """One hypothesis, checked. FR-512's flag, with its workings attached."""

    findings: tuple[CitationFinding, ...]

    @property
    def passed(self) -> bool:
        """A hypothesis resting partly on something invented is not partly
        acceptable, so one failure fails the whole."""
        return all(finding.grounded for finding in self.findings)

    @property
    def ungrounded(self) -> tuple[CitationFinding, ...]:
        return tuple(f for f in self.findings if not f.grounded)

    @property
    def near_misses(self) -> tuple[CitationFinding, ...]:
        return tuple(f for f in self.findings if f.near_miss is not None)

    @property
    def reason(self) -> str:
        """What `ai-007` records on the refusal and logs.

        Empty on a passing report: a reason present on every successful
        generation is a warning nobody can act on. A reason that does not
        say *which* claim failed leaves the investigation to start from the
        whole hypothesis, so each failure names itself.
        """
        failures = self.ungrounded
        if not failures:
            return ""
        return (
            f"{len(failures)} of {len(self.findings)} citations do not resolve "
            "against this bundle: "
            + "; ".join(
                f"citation {f.position} ({f.rule_id}/{f.finding_type}) {f.detail}"
                for f in failures
            )
        )


# ------------------------------------------------------------- the resolution


def _normalise(text: str) -> str:
    """For near-miss reporting only, and never for the verdict."""
    return "".join(text.split()).casefold()


def _citable_index(bundle: EvidenceBundle) -> dict[str, list[str]]:
    """Rule id to the finding types it appears under, in bundle order.

    A dict of lists rather than a set of pairs, because the near-miss
    detail names the types a rule actually carries and an unordered
    collection in an output path is how this repository has produced a
    result that differed between runs three times (NFR-601).

    The bundle's own `rule_id` is deliberately not here. It describes the
    claim, and a claim is not evidence for itself.
    """
    index: dict[str, list[str]] = {}
    for item in bundle.evidence:
        types = index.setdefault(item.rule_id, [])
        if item.finding_type not in types:
            types.append(item.finding_type)
    return index


def _rejected_index(bundle: EvidenceBundle) -> dict[str, list[str]]:
    """The same, over the claims `anom-013` threw out."""
    index: dict[str, list[str]] = {}
    for claim in bundle.superseded:
        types = index.setdefault(claim.rule_id, [])
        if claim.anomaly_type not in types:
            types.append(claim.anomaly_type)
    return index


def _spelling_near_miss(
    rule_id: str, finding_type: str, index: dict[str, list[str]]
) -> tuple[str, str] | None:
    """The pair this one would have matched but for case or spacing."""
    wanted = (_normalise(rule_id), _normalise(finding_type))
    for known_rule, types in index.items():
        for known_type in types:
            if (_normalise(known_rule), _normalise(known_type)) == wanted:
                return (known_rule, known_type)
    return None


def _refusal(
    position: int,
    rule_id: str,
    finding_type: str,
    citable: dict[str, list[str]],
    rejected: dict[str, list[str]],
) -> CitationFinding:
    """Why this citation failed, and how nearly it did not.

    Order matters twice here. The rejected compartment is consulted only
    after the evidence, so a pair present in both is citable. And the
    spelling near miss is looked for before the rule-id one, because both
    apply when a rule carrying several finding types is cited with one of
    them miscapitalised, and the specific reading is the useful one.
    """
    if finding_type in rejected.get(rule_id, ()):
        return CitationFinding(
            position=position,
            rule_id=rule_id,
            finding_type=finding_type,
            verdict=CitationVerdict.SUPERSEDED,
            detail=(
                "cites a claim the rule ladder rejected in favour of this one. A "
                "competing conclusion is an alternative and never support: read "
                "as evidence it turns two rules disagreeing into two rules "
                "agreeing"
            ),
        )

    spelled = _spelling_near_miss(rule_id, finding_type, citable)
    if spelled is not None:
        return CitationFinding(
            position=position,
            rule_id=rule_id,
            finding_type=finding_type,
            verdict=CitationVerdict.UNKNOWN,
            near_miss=NearMiss.CASE_OR_SPACING,
            detail=(
                f"names nothing the bundle carries; it differs from the evidence "
                f"{spelled[0]}/{spelled[1]} only in case or spacing"
            ),
        )

    spelled_rejected = _spelling_near_miss(rule_id, finding_type, rejected)
    if spelled_rejected is not None:
        return CitationFinding(
            position=position,
            rule_id=rule_id,
            finding_type=finding_type,
            verdict=CitationVerdict.UNKNOWN,
            near_miss=NearMiss.CASE_OR_SPACING,
            detail=(
                f"names nothing the bundle carries; it differs only in case or "
                f"spacing from {spelled_rejected[0]}/{spelled_rejected[1]}, which "
                "is a claim the ladder rejected and could not be cited in support "
                "even spelled correctly"
            ),
        )

    if rule_id in citable:
        return CitationFinding(
            position=position,
            rule_id=rule_id,
            finding_type=finding_type,
            verdict=CitationVerdict.UNKNOWN,
            near_miss=NearMiss.RULE_ID_UNDER_ANOTHER_TYPE,
            detail=(
                f"names a finding type {rule_id} did not produce here; the bundle "
                f"carries it as {', '.join(citable[rule_id])}"
            ),
        )

    return CitationFinding(
        position=position,
        rule_id=rule_id,
        finding_type=finding_type,
        verdict=CitationVerdict.UNKNOWN,
        detail="names nothing this bundle carries",
    )


def check(hypothesis: Hypothesis, bundle: EvidenceBundle) -> GroundingReport:
    """Resolve every citation in `hypothesis` against `bundle`.

    Pure: it reads two objects and returns a third, raising nothing for an
    ungrounded hypothesis. The raising surface `ai-007` injects is
    `GroundingChecker`, built on this rather than beside it.
    """
    citable = _citable_index(bundle)
    rejected = _rejected_index(bundle)

    findings = []
    for position, citation in enumerate(hypothesis.supporting_evidence, start=1):
        if citation.finding_type in citable.get(citation.rule_id, ()):
            findings.append(
                CitationFinding(
                    position=position,
                    rule_id=citation.rule_id,
                    finding_type=citation.finding_type,
                    verdict=CitationVerdict.GROUNDED,
                )
            )
        else:
            findings.append(
                _refusal(
                    position,
                    citation.rule_id,
                    citation.finding_type,
                    citable,
                    rejected,
                )
            )
    return GroundingReport(findings=tuple(findings))


# ------------------------------------------------------ the measurement it is


@dataclass(frozen=True, slots=True)
class GroundingRecord:
    """One hypothesis checked, attributed to the arm that produced it."""

    #: Position in the run, not in one arm's share of it. One ledger spans
    #: a run and therefore both model arms, as `ai-009`'s budget does.
    ordinal: int
    arm: GeneratorKind
    report: GroundingReport


class GroundingLedger:
    """The catch rate per arm -- a reportable result, not a side effect.

    The unit of a catch is a **hypothesis**. Counting citations would make
    one citing six kinds of evidence weigh six times what one citing a
    single kind weighs, and `eval-005` compares arms rather than claims.
    """

    def __init__(self) -> None:
        self._records: list[GroundingRecord] = []

    def record(self, arm: GeneratorKind, report: GroundingReport) -> GroundingRecord:
        entry = GroundingRecord(ordinal=len(self._records) + 1, arm=arm, report=report)
        self._records.append(entry)
        return entry

    @property
    def records(self) -> tuple[GroundingRecord, ...]:
        """A snapshot. A caller holding the live list sees a ledger that
        changes under it, which is not what a record is."""
        return tuple(self._records)

    def _for(self, arm: GeneratorKind) -> list[GroundingRecord]:
        return [record for record in self._records if record.arm is arm]

    def checked(self, arm: GeneratorKind) -> int:
        return len(self._for(arm))

    def caught(self, arm: GeneratorKind) -> int:
        return sum(1 for record in self._for(arm) if not record.report.passed)

    def catch_rate(self, arm: GeneratorKind) -> float | None:
        """Caught over checked, or `None` when nothing was checked.

        Not 0.0. Zero out of zero is unmeasured, and a rate that reports it
        as a floor makes "the check flagged nothing on this arm" true-
        looking in exactly the case where the arm never ran -- `evb-001`'s
        typed-absence principle applied to a reported result.
        """
        total = self.checked(arm)
        if total == 0:
            return None
        return self.caught(arm) / total

    def near_misses(self, arm: GeneratorKind) -> tuple[CitationFinding, ...]:
        """Every refused citation that nearly resolved, for this arm.

        What turns a catch rate into something interpretable: how many of
        the catches were one rule's findings mistaken for another's.
        """
        return tuple(
            finding
            for record in self._for(arm)
            for finding in record.report.near_misses
        )


class GroundingChecker:
    """The surface `ai-007` injects, and the one the campaign measures with.

    Callable, so it satisfies `GroundingCheck` without an adapter: raise on
    an ungrounded hypothesis, return otherwise. A predicate returning a
    bool would make *ungrounded* and *the check itself failed* the same
    answer, which is the distinction this class is most careful about --
    `ai-007`'s mutation pass found that a defect in here would otherwise
    have been recorded as the model citing something unreal, inflating a
    reported evaluation result with the checker's own fault. So nothing is
    caught and re-raised: an internal failure surfaces as itself.
    """

    def __init__(
        self, *, arm: GeneratorKind, ledger: GroundingLedger | None = None
    ) -> None:
        #: Declared, never read off the hypothesis -- see the module note.
        self.arm = arm
        self.ledger = ledger

    def report(self, hypothesis: Hypothesis, bundle: EvidenceBundle) -> GroundingReport:
        """Check, record, and hand back the workings."""
        outcome = check(hypothesis, bundle)
        if self.ledger is not None:
            self.ledger.record(self.arm, outcome)
        return outcome

    def __call__(self, hypothesis: Hypothesis, bundle: EvidenceBundle) -> None:
        """The gate. `ai-007` only ever calls this, which is why the ledger
        is fed from here and not only from `report`."""
        outcome = self.report(hypothesis, bundle)
        if not outcome.passed:
            raise GenerationRefused(outcome.reason)


__all__ = [
    "CitationFinding",
    "CitationVerdict",
    "GroundingChecker",
    "GroundingLedger",
    "GroundingRecord",
    "GroundingReport",
    "NearMiss",
    "check",
]
