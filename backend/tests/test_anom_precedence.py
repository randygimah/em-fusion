"""Reportable rule precedence. Spec: anom-013.

The three reportable rules are not three independent tests. They are one
question asked three times in a fixed order, and the reason is measured:
with no order, a background cluster of aircraft dropouts lies within the
fusion radius on 14 of 20 runs whose truth is a broken receiver, so the
fusion rule claims most of them -- and because the coverage rule is defined
never to speak about an event fusion has claimed, the wrong answer does not
merely get added. **It takes the event away from the rule that would have
been right.**

This module is the machinery that stops that. It resolves **claims**, not
rules: each rule emits a bid for a zone, the bids are ordered by a declared
constant, and a zone an earlier rule has claimed is never offered to a
later one. That shape is what lets the item be finished before `anom-006`
and `anom-005` exist -- their only obligation to it is to emit a claim.

Most of the tests below are about the ordering being a property of the
declaration rather than of the input, because an ordering that quietly
follows arrival order is the failure this item names and is also the one
that would never show up in ordinary use.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.dal.models import Location
from app.detection.precedence import (
    DEFAULT_ZONE_RADIUS_KM,
    RULE_ORDER,
    Claim,
    PrecedenceError,
    PrecedencePolicy,
    Suppression,
    Zone,
    claims_from_sensor_faults,
    resolve,
)
from app.detection.sensor_fault import (
    Confidence,
    Dismissal,
    SensorFault,
    SensorFaultFindings,
    SpatialEvidence,
    SpectralEvidence,
    Verdict,
)
from app.scenario.layout import load_layout

LAYOUT = load_layout()

FAULT = "SENSOR-FAULT"
GAP = "SOURCE-GAP"
FUSION = "FUSION-SPATIAL"

START = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
WINDOW = (START + timedelta(seconds=120), START + timedelta(seconds=420))
LATER = (START + timedelta(seconds=600), START + timedelta(seconds=900))

#: Measured from the shipped layout. RF-01 to RF-02 is 45.3 km, so the two
#: are one zone at the default radius; RF-01 to RF-04 is 104.3 km and they
#: are not.
HERE = Location(lat=52.3105, lon=4.7683)     # RF-01, Schiphol
NEAR = Location(lat=51.9569, lon=4.4375)     # RF-02, Rotterdam, 45.3 km
AWAY = Location(lat=51.45, lon=5.3745)       # RF-04, Eindhoven, 104.3 km


def zone(
    centre: Location = HERE, window: tuple[datetime, datetime] = WINDOW
) -> Zone:
    return Zone(centre=centre, started_at=window[0], ended_at=window[1])


def claim(
    rule_id: str,
    *,
    centre: Location = HERE,
    window: tuple[datetime, datetime] = WINDOW,
    anomaly_type: str = "possible_something",
) -> Claim:
    return Claim(rule_id=rule_id, anomaly_type=anomaly_type, zone=zone(centre, window))


def policy(radius: float = DEFAULT_ZONE_RADIUS_KM) -> PrecedencePolicy:
    return PrecedencePolicy(zone_radius_km=radius)


# --- the order is declared, not observed ---------------------------------


def test_the_declared_order_puts_the_receiver_fault_first() -> None:
    # spec: anom-013 -- the ordering itself, asserted rather than assumed.
    # The radio side decides the fault on evidence beyond five sigma; the
    # track side reaches a Youden's J of 0.40. Asking the weaker signal to
    # arbitrate what the stronger one settles was the original error.
    assert RULE_ORDER == (FAULT, GAP, FUSION)


def test_an_earlier_rule_claims_the_zone_and_a_later_one_does_not() -> None:
    # spec: anom-013 -- the whole point, in one case.
    result = resolve([claim(FUSION), claim(FAULT)], LAYOUT, policy())

    assert [c.rule_id for c in result.reported] == [FAULT]
    assert [s.claim.rule_id for s in result.suppressed] == [FUSION]


def test_the_outcome_does_not_depend_on_the_order_claims_arrive_in() -> None:
    # spec: anom-013 -- the item's third failure case. An implementation
    # that resolved in arrival order would pass every ordinary test and be
    # wrong exactly when two rules disagree.
    forwards = resolve([claim(FAULT), claim(GAP), claim(FUSION)], LAYOUT, policy())
    backwards = resolve([claim(FUSION), claim(GAP), claim(FAULT)], LAYOUT, policy())

    assert forwards == backwards
    assert [c.rule_id for c in forwards.reported] == [FAULT]


def test_a_sensor_fault_run_never_raises_an_interference_anomaly() -> None:
    # spec: anom-013, anom-006 -- the failure case restated where it can
    # actually be checked. Before the ordering existed this was a constraint
    # written on anom-006 that nothing enforced.
    result = resolve(
        [claim(FUSION, anomaly_type="possible_interference_zone"), claim(FAULT)],
        LAYOUT,
        policy(),
    )

    assert "possible_interference_zone" not in {c.anomaly_type for c in result.reported}


def test_at_most_one_answer_per_zone() -> None:
    # spec: anom-013 -- the item's first failure case: two reportable
    # anomalies of different types for the same zone in the same window.
    result = resolve([claim(FAULT), claim(GAP), claim(FUSION)], LAYOUT, policy())

    assert len(result.reported) == 1


# --- what counts as the same zone ---------------------------------------


def test_claims_at_different_places_are_different_zones() -> None:
    # spec: anom-013 -- RF-01 and RF-04 are 104.3 km apart, beyond any
    # radius over which one cause reaches both.
    result = resolve([claim(FAULT), claim(FUSION, centre=AWAY)], LAYOUT, policy())

    assert {c.rule_id for c in result.reported} == {FAULT, FUSION}


def test_claims_at_different_times_are_different_zones() -> None:
    # spec: anom-013 -- the same place an hour apart is not the same event,
    # which is anom-001's argument about episodes one layer up.
    result = resolve([claim(FAULT), claim(FUSION, window=LATER)], LAYOUT, policy())

    assert len(result.reported) == 2


def test_nearby_claims_in_the_same_window_are_one_zone() -> None:
    # spec: anom-013, scn-005 -- RF-01 and RF-02 are 45.3 km apart, inside
    # the radius over which scn-005 says one cause reaches two receivers.
    result = resolve([claim(FAULT), claim(FUSION, centre=NEAR)], LAYOUT, policy())

    assert [c.rule_id for c in result.reported] == [FAULT]


def test_the_zone_radius_is_configuration() -> None:
    # spec: anom-013 -- and it changes the answer, which is what makes it
    # configuration rather than a constant.
    narrow = resolve([claim(FAULT), claim(FUSION, centre=NEAR)], LAYOUT, policy(30.0))

    assert len(narrow.reported) == 2


def test_the_zone_radius_defaults_to_the_layout_discrimination_radius() -> None:
    # spec: anom-013, scn-005 -- the distance over which one cause can reach
    # two receivers, already validated there and already used by anom-007.
    # Deliberately not anom-012's 60 km, which answers a different question.
    assert DEFAULT_ZONE_RADIUS_KM == LAYOUT.discrimination_radius_km


def test_windows_meeting_at_an_instant_overlap() -> None:
    # spec: anom-013, anom-007 -- a window's end is its last contributing
    # reading and not the first quiet one, so two windows meeting at an
    # instant shared it. A strict test would let a later rule claim a zone
    # an earlier one had just finished with.
    touching = (WINDOW[1], WINDOW[1] + timedelta(seconds=300))
    result = resolve([claim(FAULT), claim(FUSION, window=touching)], LAYOUT, policy())

    assert [c.rule_id for c in result.reported] == [FAULT]


# --- suppression is between rules, never within one ----------------------


def test_two_claims_from_one_rule_are_two_events() -> None:
    # spec: anom-013 -- two broken receivers are two broken receivers. The
    # exclusion this item enforces is anom-006's with anom-005, which is
    # cross-rule by construction; applying it within a rule would silently
    # cap every rule at one finding per run.
    result = resolve([claim(FAULT), claim(FAULT, centre=NEAR)], LAYOUT, policy())

    assert len(result.reported) == 2
    assert result.suppressed == ()


def test_a_later_rule_may_still_claim_a_zone_nobody_took() -> None:
    # spec: anom-013 -- the ladder removes candidates, it does not silence
    # the later steps.
    result = resolve([claim(FUSION)], LAYOUT, policy())

    assert [c.rule_id for c in result.reported] == [FUSION]


# --- the audit trail -----------------------------------------------------


def test_a_suppression_names_the_rule_that_took_the_zone() -> None:
    # spec: anom-013, evb-001 -- "fusion was not offered this zone because
    # the receiver-fault rule claimed it" is a sentence the bundle needs.
    # A suppression a reader cannot trace is an assertion.
    result = resolve([claim(FUSION), claim(FAULT)], LAYOUT, policy())

    suppression = result.suppressed[0]
    assert isinstance(suppression, Suppression)
    assert suppression.claimed_by == FAULT
    assert FAULT in suppression.reason


def test_the_resolution_is_frozen() -> None:
    # spec: anom-013 -- a decision record that can be edited afterwards is
    # not a decision record.
    result = resolve([claim(FAULT)], LAYOUT, policy())

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reported[0].rule_id = GAP  # type: ignore[misc]


# --- refusals ------------------------------------------------------------


def test_a_rule_with_no_declared_position_is_refused() -> None:
    # spec: anom-013 -- an unknown rule has no place in the order, and
    # giving it one implicitly -- last, or by arrival -- is precisely the
    # failure case about the outcome being a property of the file.
    with pytest.raises(PrecedenceError, match="UNDECLARED"):
        resolve([claim("UNDECLARED"), claim(FAULT)], LAYOUT, policy())


def test_a_non_positive_zone_radius_is_refused() -> None:
    # spec: anom-013 -- at zero every claim is its own zone, so nothing is
    # ever suppressed and the ladder silently stops working.
    with pytest.raises(PrecedenceError):
        PrecedencePolicy(zone_radius_km=0.0)


def test_a_zone_that_ends_before_it_starts_is_refused() -> None:
    # spec: anom-013 -- an inverted window overlaps nothing and everything
    # depending on which comparison is written first.
    with pytest.raises(PrecedenceError, match="ends before"):
        Zone(centre=HERE, started_at=WINDOW[1], ended_at=WINDOW[0])


def test_nothing_in_gives_nothing_out() -> None:
    # spec: anom-013, anom-008 -- a quiet run reaches this with no claims,
    # and that must be representable rather than an error.
    result = resolve([], LAYOUT, policy())

    assert result.reported == ()
    assert result.suppressed == ()


# --- the one rule that produces claims today -----------------------------


def spatial() -> SpatialEvidence:
    return SpatialEvidence(
        radius_km=70.0,
        nominal_within_db=2.0,
        neighbours=("RF-02", "RF-03"),
        abnormal=(),
        unjudged=(),
        elevations=(("RF-02", 0.1), ("RF-03", 0.0)),
    )


def spectral() -> SpectralEvidence:
    return SpectralEvidence(
        channels=(4,),
        adjacent_checked=(3, 5),
        adjacent_abnormal=(),
        adjacent_unjudged=(),
        plan_size=8,
    )


def fault(sensor: str = "RF-01") -> SensorFault:
    site = LAYOUT.site(sensor)
    return SensorFault(
        sensor_id=sensor,
        started_at=WINDOW[0],
        ended_at=WINDOW[1],
        location=Location(lat=site.lat, lon=site.lon),
        confidence=Confidence.HIGH,
        spatial=spatial(),
        spectral=spectral(),
    )


def dismissal(sensor: str, verdict: Verdict) -> Dismissal:
    return Dismissal(
        sensor_id=sensor,
        started_at=WINDOW[0],
        ended_at=WINDOW[1],
        verdict=verdict,
        reason="because",
        spatial=spatial(),
        spectral=spectral(),
    )


def test_a_fault_becomes_a_claim_on_its_own_zone() -> None:
    # spec: anom-013, anom-007 -- the adapter, and the only producer of
    # claims that exists today.
    claims = claims_from_sensor_faults(
        SensorFaultFindings(faults=(fault(),)), LAYOUT
    )

    assert len(claims) == 1
    assert claims[0].rule_id == FAULT
    assert claims[0].anomaly_type == "possible_sensor_fault"
    assert claims[0].zone.started_at == WINDOW[0]


def test_an_undecided_verdict_is_not_a_claim() -> None:
    # spec: anom-013, anom-007 -- the three-valued verdict means what it
    # says. A rule that could not tell must not thereby block the rules
    # that might, so the zone passes to the next step untouched.
    claims = claims_from_sensor_faults(
        SensorFaultFindings(dismissed=(dismissal("RF-01", Verdict.UNDECIDED),)),
        LAYOUT,
    )

    assert claims == ()


def test_an_environmental_verdict_is_not_a_claim_either() -> None:
    # spec: anom-013, anom-007 -- the receiver-fault rule declining a zone
    # as environmental is exactly the case fusion exists for. Measured, this
    # is what 40 of 40 interference runs produce.
    claims = claims_from_sensor_faults(
        SensorFaultFindings(dismissed=(dismissal("RF-01", Verdict.ENVIRONMENTAL),)),
        LAYOUT,
    )

    assert claims == ()


def test_the_ladder_runs_end_to_end_from_a_real_rule_output() -> None:
    # spec: anom-013, anom-007 -- the one path through this item that is
    # not built from constructed claims. Fusion bids for the same zone and
    # is not offered it.
    findings = SensorFaultFindings(faults=(fault(),))
    result = resolve(
        [*claims_from_sensor_faults(findings, LAYOUT), claim(FUSION)],
        LAYOUT,
        policy(),
    )

    assert [c.anomaly_type for c in result.reported] == ["possible_sensor_fault"]
    assert result.suppressed[0].claimed_by == FAULT


def test_the_resolver_takes_no_track_evidence() -> None:
    # spec: anom-013, anom-007 -- this item orders claims and computes no
    # evidence of its own. A resolver that could reach for the track side
    # would be a fourth rule pretending to be a referee.
    parameters = set(inspect.signature(resolve).parameters)
    fields = {f.name for f in dataclasses.fields(Claim)}
    fields |= {f.name for f in dataclasses.fields(Zone)}

    assert parameters == {"claims", "layout", "policy"}
    assert not any(
        word in name
        for name in fields
        for word in ("track", "aircraft", "cluster", "gap", "excess", "severity")
    )
