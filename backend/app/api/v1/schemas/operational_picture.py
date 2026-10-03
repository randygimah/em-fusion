"""The operational picture payload. Spec: api-002.

The server half of a contract whose other half is
`frontend/src/types/operationalPicture.ts`. Nothing checks the two against each
other at compile time -- they are two declarations of one shape in two
languages -- so a test parses the TypeScript and compares field sets in both
directions. That test is the item's actual deliverable; these models are what
it holds in place.

**Field names are camelCase, and the class names match the interfaces
exactly.** `RFSensor` is not the name Python style would choose. A translation
table between the two sides is a place for them to drift while every test still
passes, so there is deliberately none.

**Absence is a value here, not a gap.** `api-002` served four of the six
sections empty because nothing produced them, with the rule that an empty
section is honest while a populated one would be invented data reaching an
analyst. The rule stands; the condition expired. `api-012` gives three of them
producers, and `hypotheses` is the one that is still empty for a reason that is
true (`api-002`, amended).

**One absence, one meaning.** `detectionSummary` is null when no detection pass
has run, and inside a summary that is present every value is a reading. That is
a change from `api-002`, which carried the absence on the two level fields, and
it was forced by checking what the store can establish: `anom-001`'s unjudged
cells are a list of cells rather than findings and nothing persists them, so
from the findings table *judged everything, found nothing* and *judged nothing*
are the same empty result. A nullability whose meaning no stored value can
establish is worse than none, because it reads as a distinction being made. The
limitation that leaves is recorded on `_receiver_health` below.

**Zero is the hard part, and it is `anom-008`'s argument at this boundary.** A
quiet run, a run nobody examined, and a pass pointed at the wrong observations
all produce no detections, and three of those are failures no property of the
output separates. `db-008` replaces findings per run per rule *including at
zero*, so the table cannot tell them apart either. What can is `anom-015`'s run
stamp -- so the question "did a detector look" is answered by the presence of
the account, and never by a number in it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.dal.models import (
    CanonicalObservation,
    DetectionPass,
    ScenarioRunSummary,
    TrackPayload,
)
from app.detection.control import REGISTER, Key, Kind, Producer
from app.detection.findings import DetectionFinding
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE_TYPE
from app.detection.fusion import RULE_ID as FUSION_RULE
from app.detection.rf_noise import ANOMALY_TYPE as RF_TYPE
from app.detection.rf_noise import RULE_ID as RF_RULE
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE
from app.detection.sensor_fault import RULE_ID as FAULT_RULE
from app.detection.track_gap import FINDING_TYPE as GAP_TYPE
from app.detection.track_gap import RULE_ID as GAP_RULE
from app.scenario.layout import RfLayout

#: Low, Medium, High -- never a percentage and never a decimal (`FR-715`,
#: `AC-11`). Declared once so the fields that carry a level cannot drift into
#: three different vocabularies, exactly as the TypeScript side declares it once.
Level = Literal["Low", "Medium", "High"]

#: One international foot is 0.3048 metres, exactly, by definition. The store
#: holds metres because the source reports them; the contract asks for feet
#: because that is what altitude is read in.
METRES_PER_FOOT = 0.3048

#: Reported when nothing has been served to say otherwise. A guess would be
#: indistinguishable from a fact on screen.
UNKNOWN = "unknown"

#: The detection layer spells a level `low`; the contract demands `Low`. Joined
#: by **enum member name** following `ai-002`, which found the trap: `.title()`
#: launders any word at all into something that looks valid and fails later, at
#: a boundary that no longer holds the row it came from.
#:
#: Written out rather than derived from `Severity`, because the right-hand side
#: has to be a member of `Level` and a derivation could not guarantee that -- a
#: fourth severity would title-case into a string the contract does not admit.
#: That every member is covered is asserted in the suite instead, so a new
#: severity fails as a test rather than as a refused request.
_LEVELS: Mapping[str, Level] = {"LOW": "Low", "MEDIUM": "Medium", "HIGH": "High"}

#: What a receiver was found to be, worst first. `fault` is an attribution to
#: the instrument; `deviating` says the readings moved and nothing blamed the
#: receiver, which is what an interference zone concluded; `nominal` is measured
#: and clean.
FAULT = "fault"
DEVIATING = "deviating"
NOMINAL = "nominal"

#: Which rule's finding puts a receiver in which state, worst first. **Declared
#: rather than derived**: `anom-008`'s register says *that* a rule produces
#: findings, not what its findings say about a receiver, and that is
#: rule-specific knowledge with no honest inference available. Declared in one
#: place so it is visible, rather than as three branches in the loop below.
#:
#: An interference zone reads `deviating` and never `fault`, which is the whole
#: of `anom-007`'s three-valued verdict: a zone *is* the environmental finding,
#: more than one receiver deviating together with the rule declining to blame
#: any of them. Marked faulty, the payload would report the opposite of what
#: the ladder decided.
RECEIVER_STATES: tuple[tuple[Key, str], ...] = (
    ((FAULT_RULE, FAULT_TYPE), FAULT),
    ((FUSION_RULE, INTERFERENCE_TYPE), DEVIATING),
    ((RF_RULE, RF_TYPE), DEVIATING),
)

#: The producers whose findings `anom-015` writes, and therefore the only ones
#: this endpoint can count. The other two registered producers ran and left no
#: rows: `anom-004`'s clusters are deliberately unstored, their citation shape
#: being one `evb-002` refuses by name, and `anom-012`'s rate excess is internal
#: to the fusion decision. They are reported as *not persisted*, which is a
#: different fact from *no such rule* -- collapsed, a built detector would read
#: as a missing one.
#:
#: Asserted against the pass's own source in `test_anom_chain.py` rather than
#: trusted: a rule that starts persisting its output must not leave this
#: endpoint reporting it unpersisted, and a pair misspelled here is silent --
#: the key simply never matches and the real count is discarded.
PERSISTED_PRODUCERS: frozenset[Key] = frozenset(
    {
        (RF_RULE, RF_TYPE),
        (GAP_RULE, GAP_TYPE),
        (FAULT_RULE, FAULT_TYPE),
        (FUSION_RULE, INTERFERENCE_TYPE),
    }
)

#: Why a producer has no count. Two reasons and never one.
RULE_NOT_BUILT = "rule-not-built"
NOT_PERSISTED = "not-persisted"

ProducerKind = Literal["intermediate", "reportable"]
CountUnavailable = Literal["rule-not-built", "not-persisted"]


class PictureError(ValueError):
    """A stored value this payload refuses to serve."""


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    dataMode: str  # noqa: N815 -- mirrors the TypeScript contract
    health: str


class Hypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    confidence: Level
    severity: Level
    status: Literal["new", "under_review", "reviewed"]
    evidence: str


class DetectionCount(BaseModel):
    """One rule and what it produced on this run. Spec: api-012, anom-008.

    Keyed on the `(rule_id, finding_type)` **pair** `ai-001` defines, because
    one does not identify: `anom-012` borrows `anom-010`'s rule id, so a rate
    excess and a discontinuity are identical by rule id while making different
    claims. The fourth place in this repository that collision has had to be
    handled.

    `kind` is carried rather than left to the screen. A quiet run genuinely
    holds about 138 track discontinuities (`anom-010`), so an intermediate count
    presented as an anomaly count reads a correct non-detection as a storm --
    and a payload without the distinction forces the screen to hard-code a list
    of rule names, which outlives the reason it was written.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ruleId: str  # noqa: N815 -- mirrors the TypeScript contract
    findingType: str  # noqa: N815 -- mirrors the TypeScript contract
    kind: ProducerKind
    count: int | None
    unavailable: CountUnavailable | None

    @model_validator(mode="after")
    def _exactly_one(self) -> DetectionCount:
        """Exactly one of the count and the reason for its absence.

        Both directions, on `EvidenceItem.grounding`'s rule: a declaration that
        can be a lie either way is not a declaration. A count beside a reason is
        unreadable; an absence nothing names is the state this field exists to
        remove, since the two reasons -- no such rule, and a rule whose output is
        not stored -- are different facts about the detection layer.
        """
        if (self.count is None) == (self.unavailable is None):
            raise PictureError(
                f"{self.ruleId}/{self.findingType} carries count={self.count!r} "
                f"and unavailable={self.unavailable!r}. Exactly one of them is "
                "the answer: a count beside a reason cannot be read, and an "
                "absence with no reason loses the difference between a rule "
                "that does not exist and one whose findings are not stored."
            )
        return self


class DetectionSummary(BaseModel):
    """What the detection pass found, for a run it examined. Spec: api-012.

    **Served only for a run that was examined**, which is why the two levels are
    not nullable: the object's own absence carries that, and a second way to say
    it would be a second thing to keep consistent.

    **The two levels are deliberately not one figure.** `anom-007` is explicit
    that confidence qualifies an *attribution* while severity qualifies a
    *deviation*, so a single number over both describes neither -- and the two
    here are not even two scales of one quantity: `anomalyLevel` is the worst
    deviation measured and `signalIntegrity` is the state of the receiver
    layout. Each has exactly one kind of thing behind it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    anomalyLevel: Level  # noqa: N815 -- mirrors the TypeScript contract
    signalIntegrity: Level  # noqa: N815 -- mirrors the contract
    #: Every registered producer, including the ones that found nothing. The
    #: presence of this list is what says the detectors looked; `anom-008`
    #: refuses to grade a run against an account missing one, because a detector
    #: that never ran and one that found nothing are the same empty result.
    counts: list[DetectionCount]


class RFSensor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    stationName: str  # noqa: N815 -- mirrors the TypeScript contract
    signalId: str  # noqa: N815 -- mirrors the TypeScript contract
    health: str
    lat: float
    lon: float


class AircraftTrack(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    #: Nullable because 22.7% of positioned rows in the corpus carry no
    #: altitude. An aircraft of unknown height is still an aircraft.
    altitudeFt: int | None  # noqa: N815 -- mirrors the TypeScript contract
    lat: float
    lon: float


class TimelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    time: str
    event: str
    source: str


class SelectableHour(BaseModel):
    """STUB -- api-013 not implemented. Fields deliberately absent."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class OperationalPicture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Null before the first run exists, so the screen can be developed and
    #: served against an empty database rather than a 500 (`op-001`).
    scenario: Scenario | None
    #: Still empty, and `api-002`'s amendment records why: 155 rows exist, so
    #: the condition that justified the other three has expired here too, and
    #: what holds this one is a decision with its own failure cases -- which
    #: arm an analyst sees, and whether a row whose grounding check FAILED may
    #: be shown at all (`db-002`).
    hypotheses: list[Hypothesis]
    #: Null when no detection pass has run on this run (`api-012`,
    #: `anom-015`). Not the same as a pass that found nothing, and the one
    #: distinction `anom-008` exists to protect.
    detectionSummary: DetectionSummary | None  # noqa: N815 -- mirrors the contract
    rfSensors: list[RFSensor]  # noqa: N815 -- mirrors the contract
    aircraftTracks: list[AircraftTrack]  # noqa: N815 -- mirrors the contract
    timelineEvents: list[TimelineEvent]  # noqa: N815 -- mirrors the contract


def _feet(metres: float | None) -> int | None:
    return None if metres is None else round(metres / METRES_PER_FOOT)


def _track(observation: CanonicalObservation) -> AircraftTrack:
    """One observation as a track.

    The name is whatever the payload holds, which `dal-004` guarantees is a
    pseudonym: the substitution happens at ingest, so nothing here has to
    remember to do it and nothing here could undo it.
    """
    payload = observation.payload
    altitude = payload.altitude_m if isinstance(payload, TrackPayload) else None
    identifier = payload.aircraft_id if isinstance(payload, TrackPayload) else ""
    return AircraftTrack(
        id=f"{observation.source_id}:{identifier}",
        name=identifier,
        altitudeFt=_feet(altitude),
        lat=observation.location.lat,
        lon=observation.location.lon,
    )


def _data_mode(observations: Sequence[CanonicalObservation]) -> str:
    """The mode of what is actually being served, not of what was asked for.

    A run row records no data mode; its observations do. Reported as `mixed`
    when they disagree rather than by taking the first, because a screen
    labelled `replayed` while showing live records is worse than one that
    admits it is showing both.
    """
    modes = {observation.data_mode.value for observation in observations}
    if not modes:
        return UNKNOWN
    if len(modes) > 1:
        return "mixed"
    return modes.pop()


def _level(word: object, *, field: str) -> Level:
    """A detection-layer level as the contract spells it. Spec: api-012, ai-002.

    By **enum member name**, never by `.title()`. `ai-002` records why: the
    casing transform launders any word at all into something that looks valid
    and only fails at a schema one layer along, by which point the row it came
    from is no longer in hand. An unfamiliar word is refused here, named, with
    the field that held it.
    """
    if isinstance(word, str) and word.upper() in _LEVELS:
        return _LEVELS[word.upper()]
    raise PictureError(
        f"a stored finding reports {field}={word!r}, which is not one of "
        f"{', '.join(name.lower() for name in _LEVELS)}. The join between the "
        "detection layer's vocabulary and the contract's is by name, so an "
        "unfamiliar word is refused rather than capitalised into something "
        "that merely looks valid."
    )


def _of(findings: Sequence[DetectionFinding], key: Key) -> list[DetectionFinding]:
    return [f for f in findings if (f.rule_id, f.finding_type) == key]


def _receivers_named(finding: DetectionFinding) -> tuple[str, ...]:
    """Which receivers a finding is about.

    Three shapes and one rule: a zone names its receivers in `details` because
    its window is the **union** of theirs (`anom-005`), a radio episode's
    subject is a sensor-channel cell, and a fault's subject is the receiver
    itself. Taking the subject alone would reduce a zone to the one receiver it
    is filed under.
    """
    sensors = finding.details.get("sensors")
    if isinstance(sensors, list):
        return tuple(str(sensor) for sensor in sensors)
    return (finding.subject.rsplit(":", 1)[0],)


def _receiver_health(
    layout: RfLayout, findings: Sequence[DetectionFinding], *, scored: bool
) -> dict[str, str]:
    """What state each receiver in the layout was found to be in.

    `unknown` until a pass has run, on the same argument `api-002` makes for
    `scenario.health`: `nominal` on an unexamined run is a reassurance nothing
    checked. The receivers themselves are served either way -- they are
    `scn-005`'s configuration, which the generator reads too, so serving them
    invents nothing.

    **A limitation, recorded rather than hidden.** `nominal` here means *no rule
    said anything about this receiver*, which on a scored run is almost always
    *measured and clean* and is not the same claim. `anom-001` reports the cells
    it cannot judge precisely so that a clean verdict cannot be satisfied by not
    having looked, and nothing persists that list -- so this boundary cannot
    distinguish a receiver measured and nominal from one with no baseline. The
    fix belongs to whatever stores the unjudged cells, not here.
    """
    if not scored:
        return {site.sensor_id: UNKNOWN for site in layout.sensors}
    state = {site.sensor_id: NOMINAL for site in layout.sensors}
    # Worst last, so a receiver both deviating and faulted reads as faulted: the
    # fault rule reads the radio rule's episodes, so the two are not exclusive
    # and the attribution is the one that matters.
    for key, value in reversed(RECEIVER_STATES):
        for finding in _of(findings, key):
            for sensor in _receivers_named(finding):
                if sensor not in state:
                    raise PictureError(
                        f"a {finding.rule_id} finding names receiver {sensor!r}, "
                        "which is not in the layout being served. The findings "
                        "were produced against a different layout, and serving "
                        "them would show a receiver as nominal while a rule had "
                        "named it."
                    )
                state[sensor] = value
    return state


def _band(layout: RfLayout) -> str:
    """The band the receivers watch, for the contract's one `signalId` field.

    **Refused rather than guessed when there is more than one.** The contract
    carries a single band per receiver and `scn-005`'s layout carries a channel
    plan, so the two agree only while that plan is one band -- which the shipped
    layout is, eight channels across GNSS-L1. Taking the first channel's band
    would label all seven receivers with it, which on a two-band layout is
    silently wrong for whichever receivers watch the other one, and wrong in the
    field an analyst reads to know what is being monitored.
    """
    bands = {channel.band for channel in layout.channels}
    if len(bands) != 1:
        raise PictureError(
            f"the layout's channel plan spans {sorted(bands)}. The contract "
            "carries one band per receiver, so there is no honest value for "
            "`signalId` here -- and the field an analyst reads to know what is "
            "being monitored is the wrong place to pick one."
        )
    return bands.pop()


def _account(
    findings: Sequence[DetectionFinding], register: Mapping[Key, Producer]
) -> list[DetectionCount]:
    """One entry per registered producer. Spec: api-012, anom-008.

    Complete, and that is the capability: `anom-008` refuses to return a verdict
    at all when a producer is missing from the account, because detectors that
    ran and found nothing, detectors that never ran and detectors pointed at the
    wrong observations all produce an identical empty result. Sorted, so a
    payload is stable across requests rather than taking its order from a
    mapping's.
    """
    entries: list[DetectionCount] = []
    for key in sorted(register):
        producer = register[key]
        unavailable = (
            RULE_NOT_BUILT
            if not producer.built
            else NOT_PERSISTED if key not in PERSISTED_PRODUCERS else None
        )
        entries.append(
            DetectionCount(
                ruleId=key[0],
                findingType=key[1],
                kind=producer.kind.value,
                count=None if unavailable else len(_of(findings, key)),
                unavailable=unavailable,  # type: ignore[arg-type]
            )
        )
    return entries


def _detection_summary(
    findings: Sequence[DetectionFinding],
    health: Mapping[str, str],
    register: Mapping[Key, Producer],
) -> DetectionSummary:
    """The two readings and the account, for a run that was examined.

    `anomalyLevel` is the **worst** deviation and never an average: a receiver
    reports on eight channels, so an average falls as the quiet ones outnumber
    the loud one, which makes a sharper incident read as a milder one. `Low`
    when nothing deviated, which is a reading rather than a stand-in for
    absence -- the summary's own presence carries that, and `anom-015` refuses a
    run with no radio readings at all, so a scored run is one whose radio side
    was read.

    `signalIntegrity` reads the receiver states and nothing else, which is what
    keeps it one kind of thing.
    """
    severities = [
        _level(finding.details.get("severity"), field="severity")
        for finding in _of(findings, (RF_RULE, RF_TYPE))
    ]
    # Written as three branches rather than a max over an ordering, so the
    # order is the code rather than a property of a list somebody can reorder.
    worst: Level = (
        "High"
        if "High" in severities
        else "Medium" if "Medium" in severities else "Low"
    )
    states = set(health.values())
    integrity: Level = (
        "Low" if FAULT in states else "Medium" if DEVIATING in states else "High"
    )
    return DetectionSummary(
        anomalyLevel=worst,
        signalIntegrity=integrity,
        counts=_account(findings, register),
    )


def _timeline(
    findings: Sequence[DetectionFinding], register: Mapping[Key, Producer]
) -> list[TimelineEvent]:
    """The reportable claims, oldest first. Spec: api-012, op-006.

    **Reportable only**, derived from the register rather than from a list of
    rule names here, so a rule that becomes reportable reaches the timeline with
    no edit. A quiet run holds about 138 discontinuities and several clusters;
    listed, they would bury the one line that is a conclusion and would present
    working material to an analyst as an event.

    The event is the finding type **verbatim** and not a sentence, which is
    `api-011`'s rule for the batch refusal: the screen composes its copy where
    the rest of that screen's copy lives, and the payload stays assertable field
    by field. The vocabulary is `ai-001`'s, shared with the grounding check and
    the scoring pack.
    """
    reportable = {
        key for key, producer in register.items() if producer.kind is Kind.REPORTABLE
    }
    claims = [f for f in findings if (f.rule_id, f.finding_type) in reportable]
    # Ordered on the **datetime** and not on the rendered string, then by the
    # two fields that make the order total. The store returns rows in whatever
    # order it finds them and `op-006` requires the ordering to be independent
    # of that; sorting the rendered form would additionally be wrong the moment
    # two rows came back with different UTC offsets, which is a property of the
    # session's timezone rather than of the data.
    claims.sort(key=lambda f: (f.started_at, f.subject, f.finding_type))
    return [
        TimelineEvent(
            id=f"{f.rule_id}:{f.subject}:{f.started_at.isoformat()}",
            time=f.started_at.isoformat(),
            event=f.finding_type,
            source=f.subject,
        )
        for f in claims
    ]


def build_operational_picture(
    *,
    run: ScenarioRunSummary | None,
    observations: Sequence[CanonicalObservation],
    layout: RfLayout,
    findings: Sequence[DetectionFinding] = (),
    detection_pass: DetectionPass | None = None,
    register: Mapping[Key, Producer] = REGISTER,
) -> OperationalPicture:
    """Assemble the payload from a run and what has been read for it.

    A pure function taking what it needs rather than a repository, so every
    judgement in the payload -- the unit conversion, the data mode, the receiver
    states, what an unexamined run may claim -- is provable without a database.

    `layout` is **required**, with no default that loads the packaged one: a
    caller that forgot it would serve an empty receiver strip, which is a
    section going quietly missing rather than a failure.

    `register` is injected, following `anom-008`'s own suite: a test asserting
    that an unbuilt rule reports no count must keep asserting the rule rather
    than the current state of `anom-006`.
    """
    scenario = (
        None
        if run is None
        else Scenario(
            id=str(run.id),
            # **Not the scenario type**, which is `api-009`'s named failure case
            # and what this field served until `api-012`: the screen's heading
            # read `gnss-degradation`, the name of the thing injected into the
            # data the detectors are being measured against. `ScenarioRunSummary`
            # was built with no ground-truth field and the check stopped there --
            # the type is not the event, it is the label for it, and it discloses
            # everything the event would. The label is the run.
            name=f"Run {run.id}",
            dataMode=_data_mode(observations),
            # No health monitoring exists. `unknown` says so; `Healthy` would
            # be a reassurance nothing has checked.
            health=UNKNOWN,
        )
    )
    scored = detection_pass is not None
    band = _band(layout)
    health = _receiver_health(layout, findings, scored=scored)
    return OperationalPicture(
        scenario=scenario,
        hypotheses=[],
        detectionSummary=(
            _detection_summary(findings, health, register) if scored else None
        ),
        rfSensors=[
            RFSensor(
                id=site.sensor_id,
                stationName=site.station_name,
                # The band this receiver watches, read off the layout and
                # identical across the seven because they share one channel
                # plan -- a fact about the layout, and refused rather than
                # guessed if that ever stops being true.
                signalId=band,
                health=health[site.sensor_id],
                lat=site.lat,
                lon=site.lon,
            )
            for site in layout.sensors
        ],
        aircraftTracks=[_track(observation) for observation in observations],
        timelineEvents=_timeline(findings, register),
    )
