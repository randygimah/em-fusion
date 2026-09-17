"""The fusion rule, `FUSION-SPATIAL`. Spec: anom-005.

The last step of the ladder, and the one whose design changed most under
measurement. As first specified it fired only when a radio anomaly and
co-located track evidence both appeared -- both conditions necessary. It
now fires on the radio pattern alone, and the track evidence is carried
beside it as corroboration.

**Why the gate went.** Under `anom-013` this rule sees almost nothing but
real interference: of 240 runs, the zones reaching it are 40 of 40
gnss-degradation, 0 of 40 aircraft-coverage-gap, 0 of 20 normal-baseline
and 1 of 40 rf-sensor-fault, and that one leak cannot be measured. A gate
at the pre-registered threshold would have reported 26 of the 40 and
rejected nothing. The 14 it would have lost all hold four or fewer track
findings in the whole run -- they are zones with almost no aircraft in
them, not zones with weak evidence. The gate would have suppressed an
interference report backed by an 8 dB deviation because few aircraft
happened to be flying nearby.

**Why the confidence does not follow the excess either.** That was this
item's own first correction and it was wrong for the same reason, softened:
a signal with a Youden's J near 0.3 must not grade a claim an 8 dB
deviation establishes. So confidence has a floor of Medium that the track
side cannot breach, and rises to High only on corroboration. This rule
never emits Low.

**Three corroboration states, not two.** A period holding no findings has a
rate consisting of nothing but `anom-012`'s smoothing constant, so the
ratio is not a comparison of two observed rates. Measured, that is the
majority case: of the 26 zones whose excess reaches the threshold, only 6
hold a finding in both periods. A disc with nothing in it during the
window is not a disc that showed no disruption -- the third time in this
layer that silence had to be separated from evidence of absence.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.dal.models import Location
from app.db.findings import save_findings
from app.db.migrations import alembic_config
from app.detection.findings import DetectionFinding
from app.detection.fusion import (
    ANOMALY_TYPE,
    DEFAULT_CORROBORATION_THRESHOLD,
    RULE_ID,
    Assessment,
    Confidence,
    Corroboration,
    FusionPolicy,
    InterferenceZone,
    assess,
    claims_from_interference,
    detect_interference,
)
from app.detection.rate_excess import RateExcess
from app.detection.sensor_fault import Confidence as FaultConfidence
from app.detection.sensor_fault import (
    Dismissal,
    SensorFault,
    SensorFaultFindings,
    SpatialEvidence,
    SpectralEvidence,
    Verdict,
)
from app.scenario.layout import load_layout
from tests.conftest import requires_database

LAYOUT = load_layout()
RUN_ID = 1
SOURCE_RULE = "TRACK-GAP"

START = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
RUN_SPAN = (START, START + timedelta(seconds=900))
WINDOW = (START + timedelta(seconds=120), START + timedelta(seconds=420))

#: RF-01 and RF-02 are 45.3 km apart and are one zone; the incident the
#: generator stages spans a centre and its neighbours inside 60 km.
HERE = Location(lat=52.3105, lon=4.7683)
NEAR = Location(lat=52.0, lon=5.06)


def excess(
    during: int, outside: int, ratio: float, centre: Location = HERE
) -> RateExcess:
    """A measured excess, as `anom-012` returns one."""
    return RateExcess(
        centre=centre,
        radius_km=60.0,
        window=WINDOW,
        during=during,
        outside=outside,
        during_per_minute=during / 5.0,
        outside_per_minute=outside / 8.0,
        ratio=ratio,
    )


def spatial(abnormal: tuple[str, ...] = ("RF-02",)) -> SpatialEvidence:
    return SpatialEvidence(
        radius_km=70.0,
        nominal_within_db=2.0,
        neighbours=("RF-02", "RF-03"),
        abnormal=abnormal,
        unjudged=(),
        elevations=(("RF-02", 8.1), ("RF-03", 0.1)),
    )


def spectral() -> SpectralEvidence:
    return SpectralEvidence(
        channels=(4,),
        adjacent_checked=(3, 5),
        adjacent_abnormal=(),
        adjacent_unjudged=(),
        plan_size=8,
    )


def dismissal(
    verdict: Verdict = Verdict.ENVIRONMENTAL,
    sensor: str = "RF-01",
    window: tuple[datetime, datetime] = WINDOW,
    abnormal: tuple[str, ...] = ("RF-02",),
) -> Dismissal:
    return Dismissal(
        sensor_id=sensor,
        started_at=window[0],
        ended_at=window[1],
        verdict=verdict,
        reason="a neighbour deviated in the same window",
        spatial=spatial(abnormal),
        spectral=spectral(),
    )


def fault(sensor: str = "RF-04") -> SensorFault:
    site = LAYOUT.site(sensor)
    return SensorFault(
        sensor_id=sensor,
        started_at=WINDOW[0],
        ended_at=WINDOW[1],
        location=Location(lat=site.lat, lon=site.lon),
        confidence=FaultConfidence.HIGH,
        spatial=spatial(abnormal=()),
        spectral=spectral(),
    )


POLICY = FusionPolicy()


# --- the judgement, which needs no database ------------------------------


def test_an_excess_past_the_threshold_on_both_periods_corroborates() -> None:
    # spec: anom-005 -- the only state in which the track side adds anything.
    result = assess(excess(during=6, outside=2, ratio=3.9), POLICY)

    assert result.corroboration is Corroboration.CORROBORATED
    assert result.confidence is Confidence.HIGH


def test_an_excess_below_the_threshold_on_both_periods_does_not() -> None:
    # spec: anom-005 -- a real measurement that came out low. The claim
    # stands on the radio evidence and is not raised.
    result = assess(excess(during=1, outside=3, ratio=0.6), POLICY)

    assert result.corroboration is Corroboration.NOT_CORROBORATED
    assert result.confidence is Confidence.MEDIUM


def test_an_empty_reference_period_is_not_measurable() -> None:
    # spec: anom-005, anom-012 -- the majority case, and the one that looks
    # most like a detection. With nothing outside the window, that period's
    # rate is nothing but anom-012's smoothing constant, so the ratio is a
    # function of the period lengths. 20 of the 26 zones whose excess
    # reaches the threshold are this.
    result = assess(excess(during=4, outside=0, ratio=7.0), POLICY)

    assert result.corroboration is Corroboration.NOT_MEASURABLE
    assert result.confidence is Confidence.MEDIUM
    assert "reference" in result.reason


def test_an_empty_window_period_is_not_measurable_either() -> None:
    # spec: anom-005 -- and this is the one that must not read as evidence
    # of absence. A disc with nothing in it during the window is not a disc
    # that showed no disruption; at these densities it is a disc nobody
    # could measure. anom-001's unjudged cells and anom-007's unmeasurable
    # neighbours make the same distinction.
    result = assess(excess(during=0, outside=3, ratio=0.18), POLICY)

    assert result.corroboration is Corroboration.NOT_MEASURABLE
    assert result.confidence is Confidence.MEDIUM


def test_a_disc_with_nothing_in_it_is_not_measurable() -> None:
    # spec: anom-005 -- both periods empty, which is 2 of the 40.
    result = assess(excess(during=0, outside=0, ratio=1.0), POLICY)

    assert result.corroboration is Corroboration.NOT_MEASURABLE


def test_an_excess_that_could_not_be_taken_at_all_is_not_measurable() -> None:
    # spec: anom-005 -- a zero-length window makes anom-012 refuse, and
    # this rule records that as unmeasurable rather than propagating it.
    # The radio evidence is unaffected by the track side failing.
    result = assess(None, POLICY)

    assert result.corroboration is Corroboration.NOT_MEASURABLE
    assert result.confidence is Confidence.MEDIUM


def test_the_threshold_is_configuration() -> None:
    # spec: anom-005, anom-012 -- and it changes the answer, which is what
    # makes it configuration rather than a constant.
    measured = excess(during=3, outside=2, ratio=2.0)
    strict = assess(measured, FusionPolicy(corroboration_threshold=3.0))
    lax = assess(measured, FusionPolicy(corroboration_threshold=1.5))

    assert strict.corroboration is Corroboration.NOT_CORROBORATED
    assert lax.corroboration is Corroboration.CORROBORATED


def test_the_threshold_defaults_to_the_pre_registered_value() -> None:
    # spec: anom-005, anom-012 -- the value batch 2 chose and batch 3 was
    # scored against out of sample, carried here rather than refitted.
    assert DEFAULT_CORROBORATION_THRESHOLD == 1.58
    assert FusionPolicy().corroboration_threshold == DEFAULT_CORROBORATION_THRESHOLD


def test_the_boundary_belongs_to_the_threshold() -> None:
    # spec: anom-005 -- an excess exactly at the threshold corroborates, so
    # the configured value names the lowest corroborating excess rather
    # than the highest non-corroborating one.
    result = assess(excess(during=3, outside=2, ratio=1.58), POLICY)

    assert result.corroboration is Corroboration.CORROBORATED


# --- what confidence may and may not do ----------------------------------


def test_the_track_side_can_raise_confidence_and_never_lower_it() -> None:
    # spec: anom-005 -- the whole argument of this item in one assertion.
    # By the time it fires, anom-007 has declined the zone as environmental,
    # which is a deviation past threshold on more than one receiver and
    # beyond five sigma. A Youden's J of 0.3 must not take that below
    # Medium.
    states = [
        assess(excess(during=6, outside=2, ratio=3.9), POLICY),
        assess(excess(during=1, outside=3, ratio=0.6), POLICY),
        assess(excess(during=4, outside=0, ratio=7.0), POLICY),
        assess(None, POLICY),
    ]

    assert states[0].confidence is Confidence.HIGH
    assert all(s.confidence is Confidence.MEDIUM for s in states[1:])


def test_this_rule_never_emits_low() -> None:
    # spec: anom-005, ui-001 -- Low exists in the vocabulary and is
    # unreachable here, which is recorded rather than left as a branch
    # nobody notices.
    everything = [
        assess(excess(d, o, r), POLICY)
        for d, o, r in (
            (6, 2, 3.9),
            (1, 3, 0.6),
            (4, 0, 7.0),
            (0, 3, 0.18),
            (0, 0, 1.0),
        )
    ] + [assess(None, POLICY)]

    assert Confidence.LOW not in {s.confidence for s in everything}


def test_confidence_is_never_a_number() -> None:
    # spec: anom-005, ui-001 -- three words, nothing else representable.
    assert {c.value for c in Confidence} == {"low", "medium", "high"}


def test_every_assessment_carries_its_reason() -> None:
    # spec: anom-005, evb-001 -- "the reference period held no findings, so
    # no rate could be compared" is a sentence the bundle needs. An
    # assessment a reader cannot check is an assertion.
    for measured in (excess(6, 2, 3.9), excess(1, 3, 0.6), excess(4, 0, 7.0), None):
        assert assess(measured, POLICY).reason


def test_an_assessment_is_frozen() -> None:
    # spec: anom-005 -- evidence that can be edited afterwards is not
    # evidence.
    result = assess(excess(during=6, outside=2, ratio=3.9), POLICY)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.confidence = Confidence.LOW  # type: ignore[misc]


def test_the_rule_carries_no_severity_or_score() -> None:
    # spec: anom-005, ui-001 -- the same structural proof anom-004 and
    # anom-012 make. Confidence is the only graded field and it is words.
    names = {f.name for f in dataclasses.fields(InterferenceZone)}
    names |= {f.name for f in dataclasses.fields(Assessment)}

    assert not names & {"severity", "score", "probability", "percent"}


# --- what becomes a zone, and what does not ------------------------------


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", empty_database.url.render_as_string(hide_password=False)
    )
    command.upgrade(config, "head")
    with empty_database.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at) "
                "VALUES (:id, 'gnss-degradation', '{}'::jsonb, 42, now())"
            ),
            {"id": RUN_ID},
        )
        connection.commit()
    return empty_database


@pytest.fixture
def factory(migrated_database: Engine) -> sessionmaker:
    return sessionmaker(bind=migrated_database, autoflush=False)


def finding(at: float, location: Location = NEAR) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=RUN_ID,
        rule_id=SOURCE_RULE,
        finding_type="track_continuity_gap",
        subject=f"AC-{at:.0f}",
        started_at=START + timedelta(seconds=at),
        ended_at=START + timedelta(seconds=at + 40),
        location=location,
        evidence_refs=({"aircraft_id": f"AC-{at:.0f}"},),
        details={"shape": "not_heard"},
    )


def detect(factory: sessionmaker, findings: SensorFaultFindings):
    return detect_interference(
        findings,
        factory,
        scenario_run_id=RUN_ID,
        run_span=RUN_SPAN,
        layout=LAYOUT,
        policy=POLICY,
    )


@pytest.mark.database
@requires_database
def test_an_environmental_zone_becomes_an_interference_anomaly(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, FR-305 -- the rule's trigger. anom-007 declining a
    # zone as environmental *is* the finding that more than one receiver
    # deviated together, which is what an interference zone is.
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=SOURCE_RULE,
        findings=[finding(150), finding(200), finding(700)],
    )

    result = detect(factory, SensorFaultFindings(dismissed=(dismissal(),)))

    assert len(result.zones) == 1
    zone = result.zones[0]
    assert zone.rule_id == RULE_ID
    assert zone.anomaly_type == ANOMALY_TYPE
    assert zone.sensors == ("RF-01", "RF-02")
    assert result.declined == ()


@pytest.mark.database
@requires_database
def test_a_zone_with_no_track_evidence_is_still_reported(
    factory: sessionmaker,
) -> None:
    # spec: anom-005 -- the gate's removal, as behaviour rather than as
    # prose. 14 of 40 staged zones hold four or fewer findings and two hold
    # none at all; suppressing them would lose a report backed by an 8 dB
    # deviation because few aircraft were nearby.
    result = detect(factory, SensorFaultFindings(dismissed=(dismissal(),)))

    assert len(result.zones) == 1
    assert result.zones[0].corroboration is Corroboration.NOT_MEASURABLE
    assert result.zones[0].confidence is Confidence.MEDIUM


@pytest.mark.database
@requires_database
def test_a_claimed_fault_never_becomes_an_interference_anomaly(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, anom-013, anom-006 -- the failure case anom-006 has
    # carried since it was written, now enforceable. A sensor-fault run
    # raising possible_interference_zone fails the spec, and the reason it
    # cannot is that anom-007 claimed the zone before this rule saw it.
    result = detect(factory, SensorFaultFindings(faults=(fault(),)))

    assert result.zones == ()
    assert result.declined == ()


@pytest.mark.database
@requires_database
def test_an_undecided_zone_is_declined_with_its_reason(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, anom-007, anom-008 -- anom-007 could not tell whether
    # the deviation was isolated, so nothing here knows it spans more than
    # one receiver. Reporting it as a zone would claim more than the
    # evidence supports; dropping it silently is what anom-008 exists to
    # prevent. It is declined, and the decline is recorded.
    result = detect(
        factory, SensorFaultFindings(dismissed=(dismissal(Verdict.UNDECIDED),))
    )

    assert result.zones == ()
    assert len(result.declined) == 1
    assert "undecided" in result.declined[0].reason.lower()


@pytest.mark.database
@requires_database
def test_a_quiet_run_produces_nothing(factory: sessionmaker) -> None:
    # spec: anom-005, anom-008 -- the correct non-detection, and the reason
    # this rule can be counted in a false-positive rate at all.
    result = detect(factory, SensorFaultFindings())

    assert result.zones == ()
    assert result.declined == ()


@pytest.mark.database
@requires_database
def test_the_excess_is_measured_over_the_zone_and_carried(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, anom-012 -- the measurement is carried whole, counts
    # included, because the counts are what say whether the ratio is a rate
    # comparison at all.
    save_findings(
        factory,
        scenario_run_id=RUN_ID,
        rule_id=SOURCE_RULE,
        findings=[finding(150), finding(200), finding(250), finding(700)],
    )

    zone = detect(factory, SensorFaultFindings(dismissed=(dismissal(),))).zones[0]

    assert zone.excess is not None
    assert zone.excess.during == 3
    assert zone.excess.outside == 1
    assert zone.corroboration is Corroboration.CORROBORATED


@pytest.mark.database
@requires_database
def test_a_zero_length_window_is_recorded_not_raised(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, anom-012 -- anom-012 refuses a window of no length,
    # and 6 of 86 runs produce one. The radio evidence does not become
    # invalid because the track side could not be measured over it.
    instant = START + timedelta(seconds=300)
    result = detect(
        factory,
        SensorFaultFindings(dismissed=(dismissal(window=(instant, instant)),)),
    )

    assert len(result.zones) == 1
    assert result.zones[0].corroboration is Corroboration.NOT_MEASURABLE
    assert result.zones[0].excess is None


@pytest.mark.database
@requires_database
def test_the_output_does_not_depend_on_the_order_of_the_input(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, NFR-601 -- determinism.
    later = (START + timedelta(seconds=600), START + timedelta(seconds=800))
    a = dismissal()
    b = dismissal(sensor="RF-05", window=later, abnormal=("RF-04",))

    forwards = detect(factory, SensorFaultFindings(dismissed=(a, b)))
    backwards = detect(factory, SensorFaultFindings(dismissed=(b, a)))

    assert forwards == backwards
    # Receivers are named in sorted order, not subject-first: a merged zone
    # has no single subject, so there is no first receiver to privilege.
    assert [z.sensors for z in forwards.zones] == [
        ("RF-01", "RF-02"),
        ("RF-04", "RF-05"),
    ]


# --- the ladder ----------------------------------------------------------


@pytest.mark.database
@requires_database
def test_a_zone_becomes_a_claim_for_the_ladder(factory: sessionmaker) -> None:
    # spec: anom-005, anom-013 -- this rule's only obligation to the
    # precedence is to emit a claim, and this is it.
    result = detect(factory, SensorFaultFindings(dismissed=(dismissal(),)))
    claims = claims_from_interference(result)

    assert len(claims) == 1
    assert claims[0].rule_id == RULE_ID
    assert claims[0].anomaly_type == ANOMALY_TYPE
    assert claims[0].zone.started_at == WINDOW[0]


@pytest.mark.database
@requires_database
def test_a_declined_zone_is_not_a_claim(factory: sessionmaker) -> None:
    # spec: anom-005, anom-013 -- this rule concluded nothing about an
    # undecided zone, so offering it to the ladder would make the
    # precedence report what the rule declined to report, and would let it
    # suppress a later rule on the strength of a non-conclusion.
    result = detect(
        factory,
        SensorFaultFindings(
            dismissed=(dismissal(), dismissal(Verdict.UNDECIDED, sensor="RF-05"))
        ),
    )
    claims = claims_from_interference(result)

    assert len(result.zones) == 1
    assert len(result.declined) == 1
    assert [c.zone.centre for c in claims] == [result.zones[0].centre]


@pytest.mark.database
@requires_database
def test_declinations_alone_produce_no_claims(factory: sessionmaker) -> None:
    # spec: anom-005, anom-008 -- a run where every candidate was undecided
    # reports nothing and says so, rather than reporting nothing silently.
    result = detect(
        factory, SensorFaultFindings(dismissed=(dismissal(Verdict.UNDECIDED),))
    )

    assert claims_from_interference(result) == ()
    assert len(result.declined) == 1


# --- one event, one zone -------------------------------------------------


def paired(
    a: str = "RF-01",
    b: str = "RF-02",
    window: tuple[datetime, datetime] = WINDOW,
) -> SensorFaultFindings:
    """What `anom-007` really emits for one interference event.

    Both receivers deviate, so both are dismissed as environmental and each
    names the other. That is one event described twice, not two events.
    """
    return SensorFaultFindings(
        dismissed=(
            dismissal(sensor=a, window=window, abnormal=(b,)),
            dismissal(sensor=b, window=window, abnormal=(a,)),
        )
    )


@pytest.mark.database
@requires_database
def test_two_receivers_in_one_event_are_one_zone(factory: sessionmaker) -> None:
    # spec: anom-005 -- found by running the ladder over the corpus, which
    # produced 160 interference zones from 60 staged runs. An incident
    # spanning two receivers has both dismissed as environmental, and one
    # zone per dismissal reports the same event twice. The same argument
    # anom-007 makes for merging a receiver's episodes, one layer up: the
    # unit of report is the event, not the evidence for it.
    result = detect(factory, paired())

    assert len(result.zones) == 1
    assert result.zones[0].sensors == ("RF-01", "RF-02")


@pytest.mark.database
@requires_database
def test_the_merged_zone_sits_between_its_receivers(factory: sessionmaker) -> None:
    # spec: anom-005 -- a zone spanning two receivers is centred between
    # them, not on whichever happened to be assessed first. The centre is
    # what anom-012's disc is measured around, so picking one end would
    # measure a patch offset from the event by half its width.
    one, two = LAYOUT.site("RF-01"), LAYOUT.site("RF-02")
    centre = detect(factory, paired()).zones[0].centre

    assert min(one.lat, two.lat) < centre.lat < max(one.lat, two.lat)
    assert min(one.lon, two.lon) < centre.lon < max(one.lon, two.lon)


@pytest.mark.database
@requires_database
def test_the_merged_window_covers_both_receivers(factory: sessionmaker) -> None:
    # spec: anom-005 -- the event ran as long as any of its evidence did.
    early = (WINDOW[0], WINDOW[0] + timedelta(seconds=100))
    late = (WINDOW[0] + timedelta(seconds=50), WINDOW[1])
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-01", window=early, abnormal=("RF-02",)),
            dismissal(sensor="RF-02", window=late, abnormal=("RF-01",)),
        )
    )

    zone = detect(factory, findings).zones[0]

    assert zone.started_at == early[0]
    assert zone.ended_at == late[1]


@pytest.mark.database
@requires_database
def test_three_receivers_deviating_together_are_one_zone(
    factory: sessionmaker,
) -> None:
    # spec: anom-005 -- membership chains: RF-04 names RF-05, RF-05 names
    # RF-06, and the three are one event even though RF-04 and RF-06 never
    # name each other. 6 of 40 staged zones span three receivers.
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-04", abnormal=("RF-05",)),
            dismissal(sensor="RF-05", abnormal=("RF-04", "RF-06")),
            dismissal(sensor="RF-06", abnormal=("RF-05",)),
        )
    )

    result = detect(factory, findings)

    assert len(result.zones) == 1
    assert result.zones[0].sensors == ("RF-04", "RF-05", "RF-06")


@pytest.mark.database
@requires_database
def test_two_events_at_the_same_time_stay_separate(factory: sessionmaker) -> None:
    # spec: anom-005 -- merging is by shared evidence and not by clock. Two
    # pairs that name nobody in common are two events however simultaneous.
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-01", abnormal=("RF-02",)),
            dismissal(sensor="RF-02", abnormal=("RF-01",)),
            dismissal(sensor="RF-06", abnormal=("RF-07",)),
            dismissal(sensor="RF-07", abnormal=("RF-06",)),
        )
    )

    result = detect(factory, findings)

    assert len(result.zones) == 2
    assert [z.sensors for z in result.zones] == [
        ("RF-01", "RF-02"),
        ("RF-06", "RF-07"),
    ]


@pytest.mark.database
@requires_database
def test_the_same_pair_in_two_windows_is_two_events(factory: sessionmaker) -> None:
    # spec: anom-005 -- and the converse: the same receivers deviating
    # again an hour later is a second event, not a longer first one. The
    # argument anom-001 makes about episodes and anom-007 about windows.
    later = (WINDOW[1] + timedelta(seconds=300), WINDOW[1] + timedelta(seconds=600))
    findings = SensorFaultFindings(
        dismissed=(*paired().dismissed, *paired(window=later).dismissed)
    )

    result = detect(factory, findings)

    assert len(result.zones) == 2
    assert result.zones[0].ended_at < result.zones[1].started_at


@pytest.mark.database
@requires_database
def test_one_merged_zone_makes_one_claim(factory: sessionmaker) -> None:
    # spec: anom-005, anom-013 -- the ladder suppresses between rules and
    # never within one, deliberately, so two claims from this rule for one
    # event would both be reported. Merging here is what makes that
    # decision safe.
    claims = claims_from_interference(detect(factory, paired()))

    assert len(claims) == 1


@pytest.mark.database
@requires_database
def test_one_receiver_naming_the_other_is_enough_to_merge(
    factory: sessionmaker,
) -> None:
    # spec: anom-005 -- the layout makes distance symmetric, so two
    # assessed receivers normally name each other and this case does not
    # arise today. The merge does not depend on that holding: a
    # one-directional test would silently split one event into two the
    # moment it stopped, and two reports of one event is the defect this
    # merging exists to remove.
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-01", abnormal=("RF-02",)),
            dismissal(sensor="RF-02", abnormal=()),
        )
    )

    result = detect(factory, findings)

    assert len(result.zones) == 1
    assert result.zones[0].sensors == ("RF-01", "RF-02")


@pytest.mark.database
@requires_database
def test_windows_meeting_at_an_instant_are_one_event(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, anom-007 -- a window's end is its last contributing
    # reading and not the first quiet one, so two meeting at an instant
    # shared it. A strict comparison would report one event twice.
    touching = (WINDOW[1], WINDOW[1] + timedelta(seconds=200))
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-01", abnormal=("RF-02",)),
            dismissal(sensor="RF-02", window=touching, abnormal=("RF-01",)),
        )
    )

    result = detect(factory, findings)

    assert len(result.zones) == 1
    assert result.zones[0].ended_at == touching[1]


@pytest.mark.database
@requires_database
def test_a_bridging_receiver_joins_two_separate_groups(
    factory: sessionmaker,
) -> None:
    # spec: anom-005 -- RF-04 and RF-06 name only RF-05, so they are two
    # groups until RF-05 arrives and belongs to both. Absorbing only the
    # first group it touches would report one event as two, and the
    # arrival order that exposes it is a property of the input rather than
    # of the evidence.
    # The windows are staggered so that dropping either absorbed group
    # changes the merged window. Asserting only on the receivers would not
    # catch it: a bridging dismissal names both, so the receiver list
    # survives even when a dismissal is lost.
    first = (WINDOW[0], WINDOW[0] + timedelta(seconds=100))
    longest = (WINDOW[0] + timedelta(seconds=50), WINDOW[1])
    bridge = (WINDOW[0] + timedelta(seconds=60), WINDOW[0] + timedelta(seconds=200))
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-06", window=first, abnormal=("RF-05",)),
            dismissal(sensor="RF-04", window=longest, abnormal=("RF-05",)),
            dismissal(sensor="RF-05", window=bridge, abnormal=("RF-04", "RF-06")),
        )
    )

    result = detect(factory, findings)

    assert len(result.zones) == 1
    assert result.zones[0].sensors == ("RF-04", "RF-05", "RF-06")
    assert result.zones[0].started_at == first[0]
    assert result.zones[0].ended_at == longest[1]


@pytest.mark.database
@requires_database
def test_zones_come_back_in_the_order_the_events_happened(
    factory: sessionmaker,
) -> None:
    # spec: anom-005, NFR-601 -- a merge appends, so an event that began
    # early but was completed late ends up behind one that began after it.
    # Here RF-01's event starts first and is finished by a dismissal that
    # arrives after RF-06's, so grouping order and time order disagree and
    # only an explicit sort puts them right.
    mid = (WINDOW[0] + timedelta(seconds=100), WINDOW[1])
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-01", abnormal=("RF-02",)),
            dismissal(sensor="RF-06", window=mid, abnormal=("RF-07",)),
            dismissal(sensor="RF-07", window=mid, abnormal=("RF-06",)),
            dismissal(
                sensor="RF-02",
                window=(WINDOW[0] + timedelta(seconds=200), WINDOW[1]),
                abnormal=("RF-01",),
            ),
        )
    )

    result = detect(factory, findings)

    assert [z.sensors for z in result.zones] == [
        ("RF-01", "RF-02"),
        ("RF-06", "RF-07"),
    ]


@pytest.mark.database
@requires_database
def test_the_merged_window_ends_at_the_latest_evidence(
    factory: sessionmaker,
) -> None:
    # spec: anom-005 -- the event ran as long as any of its evidence did,
    # whichever member happens to come first in the group. Taking one
    # member's end would cut the window short whenever a long deviation on
    # one receiver ran underneath a brief one on another.
    brief = (WINDOW[0], WINDOW[0] + timedelta(seconds=60))
    long_one = (WINDOW[0] + timedelta(seconds=30), WINDOW[1])
    findings = SensorFaultFindings(
        dismissed=(
            dismissal(sensor="RF-01", window=brief, abnormal=("RF-02",)),
            dismissal(sensor="RF-02", window=long_one, abnormal=("RF-01",)),
        )
    )

    zone = detect(factory, findings).zones[0]

    assert zone.started_at == brief[0]
    assert zone.ended_at == long_one[1]
