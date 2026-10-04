"""The evidence behind an hour's reported claims. Spec: api-015.

The payload that lets the screen say *why*. A conclusion already reaches the
analyst -- `api-012` serves it and `op-003` words it as a sentence -- and
nothing serves what it rests on, which is the project's own subject.

**The capability is the accounting and not the evidence.** The bundle already
exists, with every absence typed and every citation resolved against stored
rows. What did not exist is a shape in which *the absence of a bundle* is a
statement. Three states have to stay apart, and measured on the store of
record all three are live: 160 hours quiet, 100 hours whose claim has its
bundle, and **140 whose claim has none** -- the pass builds bundles and throws
them away, so every hour the selector offers first is in the third group.
Served as a bare list of bundles those three states are one empty list, which
is the dash `op-003` had to replace with a sentence.

**Two-sided completeness.** `explained` plus `unexplained` account for every
reported claim; `explained` plus `unclaimed` account for every stored bundle.
Nothing in the store is dropped in either direction, which makes a lost
conclusion unconstructible rather than refused: it cannot vanish by omission,
because omitting it breaks a count.

**There is no key joining the two tables, and there cannot be.** A finding is
replaced per run per rule, so a foreign key from `evidence_bundles` would
cascade-delete the bundles on every re-score -- `db-011`'s argument one table
along. They are matched on fields instead, and the match key was settled by
measurement and then by reading the two constructors. The *raw* subject cannot
be in it: `bundle.py` writes a zone's subject as `", ".join(producer.sensors)`
while `findings.py` files the claim under `zone.sensors[0]`, so a key on the
raw value misses every interference bundle in the store -- 41 of 103 -- while
matching every fault, which is a defect that looks like a feature on half a
corpus. The *head* of it can, and must: the relationship holds by
construction in both rules, and dropping the subject entirely leaves a run
with two claims in one window unable to say which bundle is whose.

**The grouping re-organises values and computes none.** `eval-007`'s
replacement constraint, which exists because its first form ("never
summarise") was backwards. Every value on a group appears verbatim on one of
its items or on the bundle's own metadata; the only arithmetic is a count of
the items a group lists. A group's span and its sources are *selections* of
values that are present.

**Two exclusions, both argued by name** (`ai-004`'s rule for its egress
exclusions). Observation row ids: not something an analyst can act on, and
the check that needs them is `ai-008`'s, which ran before anything was
stored. Item `details`: rule-internal, and whatever a person needs from them
the rule already put in its own sentence -- `power_dbm deviated by 8.40 dB at
its peak` carries the metric and the figure both -- so serving them would
make this module know what each rule's keys mean.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.detection.bundle import EvidenceBundle, EvidenceItem
from app.detection.control import REGISTER, Key, Producer, reportable_keys
from app.detection.findings import DetectionFinding

UnexplainedReason = Literal["not-bundled"]
UnclaimedReason = Literal["no-current-claim"]

#: Why a reported claim has no evidence here. One value today, and a field
#: rather than a bare absence: `api-012`'s typed-absence rule, where the
#: reason is what separates a gap in the pipeline from an hour with nothing
#: to report. Typed rather than a bare `str`, so a second reason has to be
#: added to the contract before it can be served.
NOT_BUNDLED: UnexplainedReason = "not-bundled"

#: Why a stored bundle is not attached to a claim. Live on the corpus: four
#: of 103 bundles are off by one or two sampling intervals at one end of
#: their window, written before `anom-007`'s window derivation settled.
NO_CURRENT_CLAIM: UnclaimedReason = "no-current-claim"

#: How a joined subject is split back into its first receiver. One spelling,
#: because the match key and the test asserting the relationship against the
#: two constructors have to agree about it.
SUBJECT_SEPARATOR = ", "

#: (rule id, finding type, first receiver, window start, window end).
MatchKey = tuple[str, str, str, datetime, datetime]


class EvidenceError(ValueError):
    """A stored bundle this payload refuses to serve."""


def _head(subject: str) -> str:
    """The receiver a claim is filed under, from a bundle's joined subject."""
    return subject.split(SUBJECT_SEPARATOR)[0]


class EvidenceStatement(BaseModel):
    """One wording, and which sources said it.

    `eval-007`'s factoring, which it learned on fourteen rows repeating a
    single sentence: identical wording collapses to one sentence plus its
    sources. It is a collapse of identical strings and **never** a summary --
    two neighbours measured nominal say two different things, and one
    sentence standing for both would be a sentence no rule wrote.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    count: int
    sources: list[str]


class EvidenceGroup(BaseModel):
    """Every item of one rule and one finding type.

    Keyed on `ai-001`'s **pair** and never the rule alone: `anom-012` borrows
    `anom-010`'s rule id, so a rate excess and a discontinuity are identical
    by rule id in every interference bundle this corpus produces -- the fourth
    place that collision has had to be handled, after `ai-008`'s resolution,
    `eval-007`'s grouping and `anom-008`'s register.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ruleId: str  # noqa: N815 -- mirrors the TypeScript contract
    findingType: str  # noqa: N815 -- mirrors the TypeScript contract
    #: Whether these items cite observations or state a judgement. Uniform
    #: across a group by construction and checked below, because a
    #: measurement and a judgement rendered alike invert a fault verdict: a
    #: nominal neighbour is in the bundle *precisely because* nothing was
    #: raised for it.
    grounding: Literal["observed", "derived"]
    #: Which half of the picture is invented. Per item on the bundle, because
    #: a fusion bundle spans both by definition; uniform within one pair.
    dataMode: str  # noqa: N815 -- mirrors the TypeScript contract
    #: How many items. The only arithmetic this module performs.
    count: int
    observedFrom: str  # noqa: N815 -- mirrors the TypeScript contract
    observedTo: str  # noqa: N815 -- mirrors the TypeScript contract
    sources: list[str]
    statements: list[EvidenceStatement]


class KnownUncertainty(BaseModel):
    """What the bundle does not know, and which kind of not-knowing.

    The kind crosses by **enum member name** following `ai-002`; the statement
    crosses verbatim and untruncated. A consumer handed the bare word
    `not_measurable` learns nothing it can weigh, and the three kinds
    collapsed undo `evb-001`'s organising rule at the last boundary before a
    person.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["not_applicable", "not_measurable", "measured_negative"]
    statement: str
    subject: str


class SupersededClaim(BaseModel):
    """A competing conclusion the ladder rejected.

    Outside the evidence list, always. Carried among the support, two rules'
    disagreement reads as two rules' agreement -- `ai-008`'s third verdict and
    the error it exists to catch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ruleId: str  # noqa: N815 -- mirrors the TypeScript contract
    anomalyType: str  # noqa: N815 -- mirrors the TypeScript contract
    claimedBy: str  # noqa: N815 -- mirrors the TypeScript contract
    reason: str


class ExplainedClaim(BaseModel):
    """One reported claim and the evidence behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundleId: int  # noqa: N815 -- mirrors the TypeScript contract
    ruleId: str  # noqa: N815 -- mirrors the TypeScript contract
    findingType: str  # noqa: N815 -- mirrors the TypeScript contract
    #: **The bundle's** and not the claim's: this is that bundle's own record
    #: of which receivers deviated together, which is what the panel has to
    #: name, and the claim's representative already reaches the screen through
    #: `api-012`'s timeline. Both here would be two differing values for one
    #: word in front of a reader.
    subject: str
    observedFrom: str  # noqa: N815 -- mirrors the TypeScript contract
    observedTo: str  # noqa: N815 -- mirrors the TypeScript contract
    lat: float
    lon: float
    channels: list[int]
    dataModes: list[str]  # noqa: N815 -- mirrors the TypeScript contract
    evidence: list[EvidenceGroup]
    uncertainties: list[KnownUncertainty]
    superseded: list[SupersededClaim]


class UnexplainedClaim(BaseModel):
    """A reported claim the store holds no evidence for.

    The common case rather than the edge: 140 of the 240 claim-bearing hours,
    and every hour the selector offers first.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ruleId: str  # noqa: N815 -- mirrors the TypeScript contract
    findingType: str  # noqa: N815 -- mirrors the TypeScript contract
    subject: str
    observedFrom: str  # noqa: N815 -- mirrors the TypeScript contract
    observedTo: str  # noqa: N815 -- mirrors the TypeScript contract
    reason: UnexplainedReason


class UnclaimedBundle(BaseModel):
    """Stored evidence that no current conclusion claims.

    Dropped silently, an hour would read as fully explained while some of its
    evidence was discarded -- so it is named instead. Four of 103 bundles on
    the store of record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundleId: int  # noqa: N815 -- mirrors the TypeScript contract
    ruleId: str  # noqa: N815 -- mirrors the TypeScript contract
    findingType: str  # noqa: N815 -- mirrors the TypeScript contract
    subject: str
    observedFrom: str  # noqa: N815 -- mirrors the TypeScript contract
    observedTo: str  # noqa: N815 -- mirrors the TypeScript contract
    reason: UnclaimedReason


class EvidenceAccount(BaseModel):
    """Every reported claim of one hour, and every bundle the store holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runId: int  # noqa: N815 -- mirrors the TypeScript contract
    explained: list[ExplainedClaim]
    unexplained: list[UnexplainedClaim]
    unclaimed: list[UnclaimedBundle]


def _one(values: Sequence[str], *, field: str, pair: Key) -> str:
    """The single value a group's items agree on, or a refusal.

    Both of this module's refusals are this function. A pair holding two
    groundings means a rule emitted its own finding type sometimes with
    citations and sometimes without, which is exactly the drift `evb-001`'s
    declaration exists to prevent -- so the group cannot honestly be
    labelled, and labelling it with the first value met would hide the drift
    behind a plausible payload.
    """
    distinct = sorted(set(values))
    if len(distinct) != 1:
        raise EvidenceError(
            f"the {pair[0]} / {pair[1]} items of this bundle carry "
            f"{len(distinct)} different values for {field} ({', '.join(distinct)}). "
            "Items of one rule and one finding type are one kind of evidence, "
            f"and a group labelled with one of two {field} values states "
            "something about its items that is not true of all of them."
        )
    return distinct[0]


def _statements(items: Sequence[EvidenceItem]) -> list[EvidenceStatement]:
    """The distinct wordings, each with the sources that said it."""
    order: list[str] = []
    sources: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for item in items:
        if item.finding not in sources:
            order.append(item.finding)
            sources[item.finding] = []
            counts[item.finding] = 0
        counts[item.finding] += 1
        if item.source not in sources[item.finding]:
            sources[item.finding].append(item.source)
    return [
        EvidenceStatement(text=text, count=counts[text], sources=sources[text])
        for text in order
    ]


def _groups(bundle: EvidenceBundle) -> list[EvidenceGroup]:
    """The bundle's evidence, grouped on the pair, in the builder's order.

    The order is the ladder's -- what was measured, then what was concluded
    from it -- so it is kept rather than sorted: alphabetically, a verdict
    would lead its own evidence.
    """
    order: list[Key] = []
    items: dict[Key, list[EvidenceItem]] = {}
    for item in bundle.evidence:
        pair: Key = (item.rule_id, item.finding_type)
        if pair not in items:
            order.append(pair)
            items[pair] = []
        items[pair].append(item)

    groups: list[EvidenceGroup] = []
    for pair in order:
        members = items[pair]
        sources: list[str] = []
        for member in members:
            if member.source not in sources:
                sources.append(member.source)
        groups.append(
            EvidenceGroup(
                ruleId=pair[0],
                findingType=pair[1],
                # The ignore, and not a cast: `_one` returns whichever single
                # value its items agree on, and `Grounding` has exactly the
                # two the field admits -- which the suite asserts rather than
                # the type system, as `api-012` does for the severity map.
                grounding=_one(  # type: ignore[arg-type]
                    [m.grounding.value for m in members], field="grounding", pair=pair
                ),
                dataMode=_one(
                    [m.data_mode.value for m in members], field="data mode", pair=pair
                ),
                count=len(members),
                # Selections of values that are present, not aggregates of
                # them: the earliest start and the latest end each appear
                # verbatim on one of the items.
                observedFrom=min(m.started_at for m in members).isoformat(),
                observedTo=max(m.ended_at for m in members).isoformat(),
                sources=sources,
                statements=_statements(members),
            )
        )
    return groups


def _explained(bundle_id: int, bundle: EvidenceBundle) -> ExplainedClaim:
    return ExplainedClaim(
        bundleId=bundle_id,
        ruleId=bundle.rule_id,
        findingType=bundle.anomaly_type,
        subject=bundle.subject,
        observedFrom=bundle.time_window[0].isoformat(),
        observedTo=bundle.time_window[1].isoformat(),
        lat=bundle.affected_area.lat,
        lon=bundle.affected_area.lon,
        channels=list(bundle.affected_channels),
        # Sorted, because `data_modes` is a frozenset and a payload that took
        # its order from a set's iteration would differ between processes.
        dataModes=sorted(mode.value for mode in bundle.data_modes),
        evidence=_groups(bundle),
        uncertainties=[
            KnownUncertainty(
                kind=unknown.kind.value,
                statement=unknown.statement,
                subject=unknown.subject,
            )
            for unknown in bundle.known_uncertainties
        ],
        superseded=[
            SupersededClaim(
                ruleId=loser.rule_id,
                anomalyType=loser.anomaly_type,
                claimedBy=loser.claimed_by,
                reason=loser.reason,
            )
            for loser in bundle.superseded
        ],
    )


def _keyed(
    bundles: Sequence[tuple[int, EvidenceBundle]],
) -> dict[MatchKey, tuple[int, EvidenceBundle]]:
    """The stored bundles by match key, refusing a key that is not unique.

    `evb-002`'s exactly-one-row rule one layer up. Attributed to whichever
    row came back first, the panel would show one event's evidence under
    another's conclusion and nothing anywhere would say so -- the
    unordered-result failure this repository has recorded three times.
    """
    by_key: dict[MatchKey, tuple[int, EvidenceBundle]] = {}
    for bundle_id, bundle in bundles:
        key: MatchKey = (
            bundle.rule_id,
            bundle.anomaly_type,
            _head(bundle.subject),
            bundle.time_window[0],
            bundle.time_window[1],
        )
        if key in by_key:
            raise EvidenceError(
                f"two stored bundles ({by_key[key][0]} and {bundle_id}) carry the "
                f"same claim: {key[0]} / {key[1]} on {key[2]} over {key[3]} to "
                f"{key[4]}. Only one of them can be the evidence for that "
                "conclusion, and attributing it to whichever row came back first "
                "would show one event's evidence under another's claim."
            )
        by_key[key] = (bundle_id, bundle)
    return by_key


def build_evidence_account(
    *,
    run_id: int,
    findings: Sequence[DetectionFinding],
    bundles: Sequence[tuple[int, EvidenceBundle]],
    register: Mapping[Key, Producer] = REGISTER,
) -> EvidenceAccount:
    """Every reported claim of one hour, with its evidence or with a reason.

    `findings` are **everything** the hour holds, and which of them is a
    conclusion is derived from the register rather than spelled here, so a
    rule that becomes reportable reaches this endpoint with no edit
    (`api-012`). A quiet run holds about 138 track discontinuities; listed as
    claims they would present the layer's working material as conclusions.

    The order is the order the claims arrive in, which is the findings
    reader's `started_at, subject, id`. Nothing is re-sorted here: an
    unordered payload takes its order from the heap, which this repository
    has had to fix three times, and a second ordering rule is a second place
    for two endpoints to disagree about what is newest.
    """
    reportable = reportable_keys(register)
    by_key = _keyed(bundles)
    matched: set[MatchKey] = set()

    explained: list[ExplainedClaim] = []
    unexplained: list[UnexplainedClaim] = []
    seen: set[MatchKey] = set()
    for finding in findings:
        if (finding.rule_id, finding.finding_type) not in reportable:
            continue
        key: MatchKey = (
            finding.rule_id,
            finding.finding_type,
            finding.subject,
            finding.started_at,
            finding.ended_at,
        )
        if key in seen:
            raise EvidenceError(
                f"this hour holds two reported claims with the same identity: "
                f"{key[0]} / {key[1]} on {key[2]} over {key[3]} to {key[4]}. Two "
                "broken receivers are two events, but two claims of one rule on "
                "one receiver over one window cannot be told apart, so neither "
                "can be given its own evidence."
            )
        seen.add(key)
        found = by_key.get(key)
        if found is None:
            unexplained.append(
                UnexplainedClaim(
                    ruleId=finding.rule_id,
                    findingType=finding.finding_type,
                    subject=finding.subject,
                    observedFrom=finding.started_at.isoformat(),
                    observedTo=finding.ended_at.isoformat(),
                    reason=NOT_BUNDLED,
                )
            )
            continue
        matched.add(key)
        explained.append(_explained(*found))

    unclaimed = [
        UnclaimedBundle(
            bundleId=bundle_id,
            ruleId=bundle.rule_id,
            findingType=bundle.anomaly_type,
            subject=bundle.subject,
            observedFrom=bundle.time_window[0].isoformat(),
            observedTo=bundle.time_window[1].isoformat(),
            reason=NO_CURRENT_CLAIM,
        )
        for key, (bundle_id, bundle) in by_key.items()
        if key not in matched
    ]

    return EvidenceAccount(
        runId=run_id,
        explained=explained,
        unexplained=unexplained,
        unclaimed=unclaimed,
    )
