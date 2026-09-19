"""The evidence bundle builder. Spec: evb-001.

The boundary around everything after Phase 8. Not a container -- a
*containment* boundary: it is the only thing the AI layer ever receives,
which is what makes `ai-008`'s grounding check tractable at all. Checking
"does this claim cite something real" against 20.7M observations has no
computable answer; against a closed list of evidence items it is a set
membership test.

Three things this suite pins that the item was amended to say, each of
which was wrong or absent in the specification as first written:

**The unit is one reported claim.** Not one run -- a run staging two broken
receivers is two events and `anom-013` already refuses to merge them. Not
one finding -- that is the fragmentation this item exists to prevent. The
builder consumes `anom-013`'s resolution and **does not re-group on time or
space**, because that grouping already exists and a second copy of it would
be the trap this repository recorded once over distance.

**`data_mode` is per item.** RF is ingested SYNTHETIC and replayed tracks
REPLAYED, so a fusion bundle spans both by definition -- that is what makes
it a fusion. One value on the bundle would have to be wrong, and the wrong
one is the one telling an analyst which half of the picture is invented.

**Every absence is typed.** Not-applicable, not-measurable, and measured-
and-found-nothing are three different statements and the bundle must never
let a consumer collapse them. Most of this suite is that principle in
different costumes.

Two tests here are deliberately built from **constructed findings rather
than corpus runs**, and say so: the frequency-adjacency case (all 300 runs
are narrowband, so no run can produce a wide event) and the superseded
case (188 claims bid across the corpus and 0 were suppressed). Both are
unit-testable and neither is corpus-demonstrable until the generator gains
a broadband arm and the ladder gains a second producer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.dal.models import DataMode, Location
from app.detection.baseline import RfCell
from app.detection.bundle import (BundleError, EvidenceBundle, UncertaintyKind,
                                  build_bundles)
from app.detection.findings import DetectionFinding
from app.detection.fusion import Confidence, Corroboration, InterferenceZone
from app.detection.precedence import Claim, Resolution, Suppression, Zone
from app.detection.rate_excess import RateExcess
from app.detection.rf_noise import (ReadingRef, RfNoiseAnomaly, RfNoiseFindings,
                                    Severity, SuppressedEpisode, UnjudgedCell)
from app.detection.sensor_fault import (SensorFault, SpatialEvidence, SpectralEvidence,
                                        Verdict)
from app.detection.baseline import RfMetric

START = datetime(2022, 6, 27, 12, 0, tzinfo=timezone.utc)
END = START + timedelta(seconds=300)
HERE = Location(lat=51.5, lon=6.0)
THERE = Location(lat=52.9, lon=9.4)
RUN = 412


def episode(sensor: str, channel: int, *, started=START, ended=END,
            severity=Severity.HIGH, peak=8.4) -> RfNoiseAnomaly:
    cell = RfCell(sensor_id=sensor, channel_index=channel)
    return RfNoiseAnomaly(
        cell=cell, metric=RfMetric.POWER_DBM, severity=severity,
        started_at=started, ended_at=ended, location=HERE, peak_deviation=peak,
        triggering=(ReadingRef(sensor_id=sensor, channel_index=channel,
                               timestamp=started),))


def spatial(*, neighbours=("RF-02", "RF-05"), abnormal=(), unjudged=()) -> SpatialEvidence:
    return SpatialEvidence(
        radius_km=85.0, nominal_within_db=2.0, neighbours=neighbours,
        abnormal=abnormal, unjudged=unjudged,
        elevations=tuple((s, 0.4) for s in neighbours))


def spectral(*, channels=(4,), adjacent_checked=(3, 5), adjacent_abnormal=(),
             adjacent_unjudged=()) -> SpectralEvidence:
    return SpectralEvidence(
        channels=channels, adjacent_checked=adjacent_checked,
        adjacent_abnormal=adjacent_abnormal, adjacent_unjudged=adjacent_unjudged,
        plan_size=8)


def fault(sensor="RF-03", **kw) -> SensorFault:
    return SensorFault(
        sensor_id=sensor, started_at=START, ended_at=END, location=HERE,
        confidence=Confidence.HIGH, spatial=kw.pop("spatial", spatial()),
        spectral=kw.pop("spectral", spectral()))


def zone(*, sensors=("RF-03", "RF-04"), centre=HERE,
         corroboration=Corroboration.CORROBORATED, excess=None,
         started=START, ended=END) -> InterferenceZone:
    if excess is None and corroboration is not Corroboration.NOT_MEASURABLE:
        excess = RateExcess(
            centre=centre, radius_km=60.0, window=(started, ended),
            during=14, outside=3, during_per_minute=2.8, outside_per_minute=0.3,
            ratio=9.61)
    return InterferenceZone(
        sensors=sensors, centre=centre, started_at=started, ended_at=ended,
        corroboration=corroboration, confidence=Confidence.HIGH, excess=excess,
        reason="two receivers deviated together")


def claim_for(source) -> Claim:
    z = Zone(centre=source.location if isinstance(source, SensorFault) else source.centre,
             started_at=source.started_at, ended_at=source.ended_at)
    return Claim(rule_id=source.rule_id, anomaly_type=source.anomaly_type, zone=z)


def track_finding(pseudonym="AC-48089ab4e5a9", at=START) -> DetectionFinding:
    return DetectionFinding(
        scenario_run_id=RUN, rule_id="TRACK-GAP", finding_type="track_discontinuity",
        subject=pseudonym, started_at=at, ended_at=at + timedelta(seconds=120),
        location=HERE,
        evidence_refs=({"aircraft_id": pseudonym, "at": at.isoformat()},))


def build(reported, *, faults=(), zones=(), rf=None, tracks=(), suppressed=()):
    return build_bundles(
        Resolution(reported=tuple(reported), suppressed=tuple(suppressed)),
        scenario_run_id=RUN, faults=tuple(faults), zones=tuple(zones),
        rf=rf or RfNoiseFindings(), track_findings=tuple(tracks))


# --------------------------------------------------------------- the unit

def test_one_reported_claim_makes_one_bundle():
    # spec: evb-001 -- the unit is a claim, and the item's phrase "a group of
    # related anomalies from one scenario run" predates the ladder.
    f = fault()
    bundles = build([claim_for(f)], faults=[f], rf=RfNoiseFindings(
        anomalies=(episode("RF-03", 4),)))
    assert len(bundles) == 1
    assert bundles[0].anomaly_type == f.anomaly_type


def test_two_events_in_one_run_make_two_bundles():
    # spec: evb-001 -- a run with two broken receivers is two events.
    # anom-013 already refuses to merge them (suppression is cross-rule
    # only), so a builder grouping by run would silently cap each run at one.
    a = fault("RF-03")
    b = SensorFault(sensor_id="RF-07", started_at=START, ended_at=END,
                    location=THERE, confidence=Confidence.HIGH,
                    spatial=spatial(), spectral=spectral())
    bundles = build([claim_for(a), claim_for(b)], faults=[a, b],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),
                                                  episode("RF-07", 4))))
    assert len(bundles) == 2
    assert {bundle.subject for bundle in bundles} == {"RF-03", "RF-07"}


def test_the_builder_does_not_regroup_nearby_claims():
    # spec: evb-001 -- time and space grouping is anom-013's, already
    # measured, and a second implementation here would be the second copy of
    # a rule that this repository has recorded falling into once over
    # distance. Two claims the ladder kept apart stay apart, however close.
    a = fault("RF-03")
    b = SensorFault(sensor_id="RF-04", started_at=START, ended_at=END,
                    location=Location(lat=51.51, lon=6.01),  # ~1 km away
                    confidence=Confidence.HIGH, spatial=spatial(),
                    spectral=spectral())
    bundles = build([claim_for(a), claim_for(b)], faults=[a, b],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),
                                                  episode("RF-04", 4))))
    assert len(bundles) == 2


def test_a_quiet_run_produces_no_bundles_rather_than_an_empty_one():
    # spec: evb-001, anom-008 -- the two requirements agree, and the way
    # they agree is that nothing is created. An empty bundle per quiet run
    # would satisfy neither and would put 60 content-free objects in front
    # of a model.
    assert build([]) == ()


def test_a_claim_with_no_producer_is_refused():
    # spec: evb-001 -- a reported claim whose source object was not supplied
    # is a programming error, and building a bundle without its evidence
    # would produce exactly the empty-evidence bundle the item forbids.
    with pytest.raises(BundleError):
        build([claim_for(fault())], faults=[])


# ------------------------------------------------- the two stated failures

def test_an_evidence_item_without_a_rule_id_is_refused():
    # spec: evb-001 (stated failure case), FR-402 -- the rule ID is what
    # makes an explanation checkable, so an item without one is not evidence.
    f = fault()
    bundles = build([claim_for(f)], faults=[f],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    assert all(item.rule_id for item in bundles[0].evidence)
    with pytest.raises(BundleError):
        bundles[0].with_evidence(
            tuple(item.without_rule_id() for item in bundles[0].evidence))


def test_a_bundle_with_no_evidence_is_refused():
    # spec: evb-001 (stated failure case) -- a bundle asserting an event
    # with nothing behind it is the thing this object exists to prevent.
    with pytest.raises(BundleError):
        EvidenceBundle(
            scenario_run_id=RUN, anomaly_type="possible_sensor_fault",
            rule_id="SENSOR-FAULT", subject="RF-03", time_window=(START, END),
            affected_area=HERE, affected_channels=(4,), evidence=(),
            known_uncertainties=())


def test_adjacent_channels_of_one_sensor_group_into_one_bundle():
    # spec: evb-001 (second stated failure case) -- a broadband event raises
    # every channel of an affected receiver, and grouped on time and space
    # alone that is eight findings about eight channels: one coherent event
    # fragmented into eight, handed to a model as an incoherent picture it
    # will then explain as eight things.
    #
    # CONSTRUCTED, NOT FROM THE CORPUS, and deliberately: all 300 runs of
    # corpus v2 are narrowband, as all 240 of v1 were, so no available run
    # can produce a wide event. This proves the mechanism; that the
    # mechanism matters is owed to a broadband generation arm that does not
    # exist. Recorded on the item rather than discovered in a write-up.
    wide = fault(spectral=spectral(channels=(0, 1, 2, 3, 4, 5, 6, 7),
                                   adjacent_checked=(), adjacent_abnormal=()))
    rf = RfNoiseFindings(anomalies=tuple(
        episode("RF-03", channel) for channel in range(8)))
    bundles = build([claim_for(wide)], faults=[wide], rf=rf)
    assert len(bundles) == 1
    assert bundles[0].affected_channels == tuple(range(8))
    assert len(bundles[0].evidence) >= 8


# ----------------------------------------------------- data mode, per item

def test_a_fusion_bundle_spans_both_data_modes():
    # spec: evb-001 (amended) -- RF is ingested SYNTHETIC and replayed
    # tracks REPLAYED, so a fusion bundle draws on both by definition. A
    # single data_mode on the bundle would have to be wrong, and op-001's
    # SYNTHETIC ENVIRONMENT DATA badge is specified to reflect the data
    # rather than a UI constant.
    z = zone()
    bundles = build([claim_for(z)], zones=[z], tracks=[track_finding()],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),
                                                  episode("RF-04", 4))))
    assert bundles[0].data_modes == frozenset({DataMode.SYNTHETIC,
                                               DataMode.REPLAYED})
    assert {item.data_mode for item in bundles[0].evidence} == bundles[0].data_modes


def test_every_evidence_item_carries_its_own_data_mode():
    # spec: evb-001 (amended) -- the mode belongs to the observation, not to
    # the bundle, so an RF item says synthetic even inside a fused bundle.
    z = zone()
    bundles = build([claim_for(z)], zones=[z], tracks=[track_finding()],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    by_rule = {item.rule_id: item.data_mode for item in bundles[0].evidence}
    assert by_rule["RF-NOISE"] is DataMode.SYNTHETIC
    assert by_rule["TRACK-GAP"] is DataMode.REPLAYED


# --------------------------------------------- every absence is typed

def test_not_measurable_corroboration_carries_its_reason_not_just_a_flag():
    # spec: evb-001 (amended), anom-005 -- this is the 41-of-60 case and the
    # most consequential uncertainty the system produces. A period holding
    # no findings has a rate made of nothing but anom-012's smoothing
    # constant, so the ratio is not a comparison of two observed rates. The
    # bundle must say that, because the project's fusion claim is weaker
    # than it sounds and this object is what tells the model so.
    z = zone(corroboration=Corroboration.NOT_MEASURABLE, excess=None)
    bundles = build([claim_for(z)], zones=[z],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    unmeasurable = [u for u in bundles[0].known_uncertainties
                    if u.kind is UncertaintyKind.NOT_MEASURABLE]
    assert len(unmeasurable) == 1
    assert unmeasurable[0].statement.strip()
    assert unmeasurable[0].statement != Corroboration.NOT_MEASURABLE.value


def test_measured_and_found_nothing_is_evidence_not_an_uncertainty():
    # spec: evb-001 (amended) -- not_corroborated means the track side WAS
    # measured and showed no elevated rate. That is a negative finding and
    # belongs in the evidence list; filing it as not-measurable would claim
    # ignorance the system does not have, which is the same collapse this
    # bundle exists to prevent, pointed the other way.
    z = zone(corroboration=Corroboration.NOT_CORROBORATED)
    bundles = build([claim_for(z)], zones=[z],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    assert any(item.rule_id == "TRACK-RATE-EXCESS" for item in bundles[0].evidence)
    assert not any(u.kind is UncertaintyKind.NOT_MEASURABLE
                   for u in bundles[0].known_uncertainties)


def test_a_sensor_fault_bundle_states_the_track_side_is_not_applicable():
    # spec: evb-001 (amended) -- a single-receiver fault verdict never
    # reaches anom-005, so there is no track evidence BY DESIGN. Left absent
    # it reads as not-measurable, which would be a false uncertainty claim
    # and the mirror image of the corroboration problem above.
    f = fault()
    bundles = build([claim_for(f)], faults=[f],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    not_applicable = [u for u in bundles[0].known_uncertainties
                      if u.kind is UncertaintyKind.NOT_APPLICABLE]
    assert len(not_applicable) == 1
    assert not any(u.kind is UncertaintyKind.NOT_MEASURABLE
                   for u in bundles[0].known_uncertainties)


def test_nominal_neighbours_are_positive_evidence_with_their_margins():
    # spec: evb-001 (amended), anom-007 -- a neighbour measured and found
    # nominal is the discriminating observation that makes this a fault
    # rather than the environment. It is evidence, not an absence, and the
    # margin is what an analyst would check.
    f = fault(spatial=spatial(neighbours=("RF-02", "RF-05")))
    bundles = build([claim_for(f)], faults=[f],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    nominal = [item for item in bundles[0].evidence
               if item.source in {"RF-02", "RF-05"}]
    assert len(nominal) == 2
    assert all(item.rule_id == "SENSOR-FAULT" for item in nominal)
    assert all("db" in item.details for item in nominal)


def test_unjudged_cells_and_channels_become_uncertainties():
    # spec: evb-001 (amended), anom-001, anom-007 -- "I had no baseline, so
    # I did not look" is not "I looked and saw nothing", and only the second
    # is evidence.
    f = fault(spatial=spatial(unjudged=("RF-06",)),
              spectral=spectral(adjacent_unjudged=(5,)))
    rf = RfNoiseFindings(
        anomalies=(episode("RF-03", 4),),
        unjudged=(UnjudgedCell(cell=RfCell(sensor_id="RF-08", channel_index=2),
                               reason="no baseline"),))
    bundles = build([claim_for(f)], faults=[f], rf=rf)
    kinds = [u.kind for u in bundles[0].known_uncertainties]
    assert kinds.count(UncertaintyKind.NOT_MEASURABLE) >= 2


def test_suppressed_episodes_are_reported_as_looked_at_and_too_brief():
    # spec: evb-001 (amended), anom-014 -- "I looked and it was too brief to
    # call an event" is a third statement again, and anom-014 gave it its
    # own field rather than folding it into the unjudged cells precisely so
    # this distinction survives to here.
    f = fault()
    rf = RfNoiseFindings(
        anomalies=(episode("RF-03", 4),),
        suppressed=(SuppressedEpisode(
            cell=RfCell(sensor_id="RF-03", channel_index=6),
            started_at=START, ended_at=START, readings=1,
            minimum=timedelta(seconds=10)),))
    bundles = build([claim_for(f)], faults=[f], rf=rf)
    brief = [u for u in bundles[0].known_uncertainties
             if u.kind is UncertaintyKind.MEASURED_NEGATIVE]
    assert len(brief) == 1


# ------------------------------------------------------ superseded claims

def test_a_superseded_claim_is_carried_but_never_as_evidence():
    # spec: evb-001 (amended), ai-008 -- a suppressed claim is another
    # rule's COMPETING conclusion about the same place, so the likeliest
    # misreading is that co-occurrence is concurrence: a consumer handed
    # both writes that two independent rules flagged this area, which
    # inverts the truth exactly. Dropping it would make the bundle assert
    # more confidence than the system has, so it is carried outside the
    # evidence list.
    #
    # CONSTRUCTED, NOT FROM THE CORPUS: 188 claims are bid across corpus v2
    # and 0 are suppressed, because exactly one rule bids per run. This path
    # is dormant until a second producing rule exists.
    f = fault()
    loser = Claim(rule_id="SOURCE-GAP", anomaly_type="possible_data_source_issue",
                  zone=claim_for(f).zone)
    bundles = build([claim_for(f)], faults=[f],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)),
                    suppressed=[Suppression(claim=loser, claimed_by="SENSOR-FAULT",
                                            reason="an earlier rule claimed this zone")])
    assert len(bundles[0].superseded) == 1
    assert bundles[0].superseded[0].rule_id == "SOURCE-GAP"
    assert "SOURCE-GAP" not in {item.rule_id for item in bundles[0].evidence}


def test_a_superseded_claim_names_the_rule_that_won_and_why():
    # spec: evb-001 (amended) -- phrased as a resolved competition rather
    # than as a bare co-occurring fact, because the phrasing is what stops
    # it reading as support.
    f = fault()
    loser = Claim(rule_id="SOURCE-GAP", anomaly_type="possible_data_source_issue",
                  zone=claim_for(f).zone)
    bundles = build([claim_for(f)], faults=[f],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)),
                    suppressed=[Suppression(claim=loser, claimed_by="SENSOR-FAULT",
                                            reason="an earlier rule claimed this zone")])
    superseded = bundles[0].superseded[0]
    assert superseded.claimed_by == "SENSOR-FAULT"
    assert superseded.reason.strip()


def test_a_suppression_for_another_zone_does_not_reach_this_bundle():
    # spec: evb-001 -- suppressions belong to the zone they were suppressed
    # in. Attaching every run's suppressions to every bundle would put a
    # competing explanation for somewhere else beside this event.
    a = fault("RF-03")
    b = SensorFault(sensor_id="RF-07", started_at=START, ended_at=END,
                    location=THERE, confidence=Confidence.HIGH,
                    spatial=spatial(), spectral=spectral())
    elsewhere = Claim(rule_id="SOURCE-GAP",
                      anomaly_type="possible_data_source_issue",
                      zone=claim_for(b).zone)
    bundles = build([claim_for(a)], faults=[a],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)),
                    suppressed=[Suppression(claim=elsewhere, claimed_by="SENSOR-FAULT",
                                            reason="an earlier rule claimed this zone")])
    assert bundles[0].superseded == ()


# ------------------------------------------------------------- boundaries

def test_the_bundle_carries_no_ground_truth():
    # spec: evb-001, api-009 -- a consumer that can see the answer key
    # invalidates every metric computed from it. The answer lives on the run
    # record and nowhere else.
    f = fault()
    bundles = build([claim_for(f)], faults=[f],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    forbidden = {"ground_truth", "staged", "answer", "injected", "scenario_type"}
    assert not (forbidden & set(vars(bundles[0]) if hasattr(bundles[0], "__dict__")
                                else {f: None for f in bundles[0].__slots__}))


def test_no_raw_aircraft_identifier_reaches_a_bundle():
    # spec: evb-001, NFR-405, dal-004 -- the bundle is the last point before
    # data leaves the machine, and NFR-405 names this object explicitly.
    # Pseudonymisation happens far upstream, so the guarantee is INHERITED
    # -- and inherited is not proved, which is why this test exists.
    z = zone()
    bundles = build([claim_for(z)], zones=[z], tracks=[track_finding()],
                    rf=RfNoiseFindings(anomalies=(episode("RF-03", 4),)))
    rendered = repr(bundles[0])
    assert "AC-" in rendered
    assert "icao24" not in rendered


def test_the_same_inputs_build_the_same_bundle():
    # spec: evb-001, NFR-601 -- the campaign compares hypothesis quality
    # across generator arms over IDENTICAL bundles. If bundle content varied
    # with anything but the run, a difference in hypothesis quality could
    # not be attributed to the generator, and the comparison would stop
    # being a comparison.
    f = fault()
    rf = RfNoiseFindings(anomalies=(episode("RF-03", 4),))
    first = build([claim_for(f)], faults=[f], rf=rf)
    second = build([claim_for(f)], faults=[f], rf=rf)
    assert first == second
