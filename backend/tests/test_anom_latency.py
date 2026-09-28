"""Detection latency, in simulated time. Spec: anom-009.

**The definition is the item, and the obvious one does not survive contact
with the build.** "When the detector noticed, minus when the event began" has
no second term here: detection is batch, the rules read a completed run out
of the store, and there is no instant at which a rule emits. Written without
settling that, the measurement reaches for whichever timestamp is nearest --
and the nearest is a stored bundle's `created_at`, which is wall clock in a
simulated-time costume and is the failure case the item names.

What is real is **how much of an incident must elapse before the evidence a
rule demands is complete**. That is a property of the rule's design, it is
what a streaming version would face too, and it is the figure worth
reporting -- provided nobody calls it how fast the software is.

Two facts about the built rules shape everything below. The rules do not
retain the episodes they rest on, so the declaration lives in a registry
rather than on the claim; and `anom-005`'s zone window is the **union** of
its receivers' windows, so a single formula for both rules would understate
interference latency by however long the receivers were staggered.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.detection.fusion import RULE_ID as FUSION
from app.detection.precedence import Claim, PrecedenceError, Zone
from app.detection.rf_noise import DEFAULT_MINIMUM_DURATION
from app.detection.sensor_fault import RULE_ID as FAULT
from tests.test_evb_bundle import HERE, episode

ONSET = datetime(2022, 6, 27, 12, 10, tzinfo=timezone.utc)
STEP = timedelta(seconds=10)
MINIMUM = DEFAULT_MINIMUM_DURATION


def claim(rule_id=FAULT, *, started=ONSET, ended=None) -> Claim:
    return Claim(
        rule_id=rule_id,
        anomaly_type="possible_sensor_fault",
        zone=Zone(
            centre=HERE,
            started_at=started,
            ended_at=ended if ended is not None else started + timedelta(seconds=300),
        ),
    )


def at(seconds: int) -> datetime:
    """A simulated instant, as an offset from the staged onset."""
    return ONSET + timedelta(seconds=seconds)


# ------------------------------------------------------------ the arithmetic


def test_latency_is_the_evidence_requirement_not_the_window_start() -> None:
    # spec: anom-009 -- the worked example the definition was fixed on.
    #
    # Interference staged at 12:10. The first deviating reading lands at
    # 12:10:10 and the second at 12:10:20, and only then has the episode run
    # for the 10 s minimum. The rule could not honestly have committed
    # before that, so the latency is 20 s -- not 10, which is when the
    # evidence started, and not 0, which is when the event did.
    from app.detection.latency import measure

    measured = measure(
        claim(FAULT, started=at(10)),
        sensors=("RF-01",),
        onset=ONSET,
        episodes=[episode("RF-01", 4, started=at(10), ended=at(60))],
        minimum=MINIMUM,
    )

    assert measured.decidable_at == at(20)
    assert measured.latency == timedelta(seconds=20)


def test_a_rule_needing_two_receivers_waits_for_the_second() -> None:
    # spec: anom-009 -- the fact that makes one formula for both rules wrong.
    #
    # `anom-005`'s window is the **union** of its receivers', so it starts
    # when the *first* receiver does. But the rule's claim is that more than
    # one deviated together, so it cannot commit until the second one's
    # evidence is sufficient. Measured from the union's start this would
    # read 20 s; the true answer is 50 s.
    from app.detection.latency import measure

    measured = measure(
        claim(FUSION, started=at(10)),
        sensors=("RF-01", "RF-02"),
        onset=ONSET,
        episodes=[
            episode("RF-01", 4, started=at(10), ended=at(90)),
            episode("RF-02", 4, started=at(40), ended=at(90)),
        ],
        minimum=MINIMUM,
    )

    assert measured.decidable_at == at(50)
    assert measured.latency == timedelta(seconds=50)


def test_a_receiver_qualifies_on_its_earliest_episode() -> None:
    # spec: anom-009 -- a receiver deviating twice decided on the first one.
    from app.detection.latency import measure

    measured = measure(
        claim(FAULT, started=at(10)),
        sensors=("RF-01",),
        onset=ONSET,
        episodes=[
            episode("RF-01", 4, started=at(200), ended=at(260)),
            episode("RF-01", 4, started=at(10), ended=at(60)),
        ],
        minimum=MINIMUM,
    )

    assert measured.decidable_at == at(20)


def test_episodes_on_receivers_the_claim_is_not_about_are_ignored() -> None:
    # spec: anom-009 -- a run holds every receiver's episodes, and a third
    # one deviating earlier elsewhere is not evidence for this claim.
    from app.detection.latency import measure

    measured = measure(
        claim(FAULT, started=at(40)),
        sensors=("RF-01",),
        onset=ONSET,
        episodes=[
            episode("RF-09", 4, started=at(0), ended=at(60)),
            episode("RF-01", 4, started=at(40), ended=at(90)),
        ],
        minimum=MINIMUM,
    )

    assert measured.decidable_at == at(50)


# -------------------------------------------------------- how it is reported


def test_a_negative_latency_is_reported_and_never_clamped() -> None:
    # spec: anom-009 -- the constraint that keeps the measurement honest.
    #
    # Evidence beginning before the staged onset means the rule swept in
    # readings from outside the incident. Clamped to zero that reads as
    # instant detection, which is the opposite of what it says.
    from app.detection.latency import measure

    measured = measure(
        claim(FAULT, started=at(-60)),
        sensors=("RF-01",),
        onset=ONSET,
        episodes=[episode("RF-01", 4, started=at(-60), ended=at(60))],
        minimum=MINIMUM,
    )

    assert measured.latency == timedelta(seconds=-50)
    assert measured.latency < timedelta(0)


def test_the_measurement_carries_the_resolution_it_was_taken_at() -> None:
    # spec: anom-009 -- the value is quantised to the sampling interval, so
    # a figure without its interval invites sub-interval precision that the
    # corpus cannot support.
    from app.detection.latency import measure

    measured = measure(
        claim(FAULT, started=at(10)),
        sensors=("RF-01",),
        onset=ONSET,
        episodes=[episode("RF-01", 4, started=at(10), ended=at(60))],
        minimum=MINIMUM,
    )

    assert measured.minimum == MINIMUM
    assert measured.as_json()["minimum_seconds"] == MINIMUM.total_seconds()
    assert measured.as_json()["latency_seconds"] == 20.0


def test_nothing_here_reads_a_clock() -> None:
    # spec: anom-009 -- the stated failure case is a latency that changes
    # when the same run is replayed on faster hardware. Proved by measuring
    # the same inputs twice with real time passing in between, rather than
    # asserted in a comment.
    import time

    from app.detection.latency import measure

    arguments = dict(
        sensors=("RF-01",),
        onset=ONSET,
        episodes=[episode("RF-01", 4, started=at(10), ended=at(60))],
        minimum=MINIMUM,
    )
    first = measure(claim(FAULT, started=at(10)), **arguments)
    time.sleep(0.01)
    second = measure(claim(FAULT, started=at(10)), **arguments)

    assert first == second


# ------------------------------------------------------------- the refusals


def test_a_rule_with_no_declared_requirement_is_refused() -> None:
    # spec: anom-009 -- `anom-013`'s own rule. A default would measure a new
    # rule as though it needed one receiver, which is a number about a
    # question nobody asked.
    from app.detection.latency import measure

    with pytest.raises(PrecedenceError, match="INVENTED-RULE"):
        measure(
            claim("INVENTED-RULE", started=at(10)),
            sensors=("RF-01",),
            onset=ONSET,
            episodes=[episode("RF-01", 4, started=at(10), ended=at(60))],
            minimum=MINIMUM,
        )


def test_too_few_contributing_receivers_is_refused() -> None:
    # spec: anom-009 -- the evidence the rule says it needs was never there,
    # so a number computed anyway would describe nothing.
    from app.detection.latency import measure

    with pytest.raises(PrecedenceError, match="2"):
        measure(
            claim(FUSION, started=at(10)),
            sensors=("RF-01", "RF-02"),
            onset=ONSET,
            episodes=[episode("RF-01", 4, started=at(10), ended=at(90))],
            minimum=MINIMUM,
        )


def test_a_claim_with_no_episodes_at_all_is_refused() -> None:
    # spec: anom-009 -- the same refusal at its limit, and the one a caller
    # hits when it passes another run's episodes by mistake.
    from app.detection.latency import measure

    with pytest.raises(PrecedenceError):
        measure(
            claim(FAULT, started=at(10)),
            sensors=("RF-01",),
            onset=ONSET,
            episodes=[],
            minimum=MINIMUM,
        )


def test_a_negative_minimum_is_refused() -> None:
    # spec: anom-009 -- it would move every latency earlier than the
    # evidence that produced it.
    from app.detection.latency import measure

    with pytest.raises(PrecedenceError, match="minimum"):
        measure(
            claim(FAULT, started=at(10)),
            sensors=("RF-01",),
            onset=ONSET,
            episodes=[episode("RF-01", 4, started=at(10), ended=at(60))],
            minimum=timedelta(seconds=-1),
        )


def test_the_requirement_table_covers_every_claiming_rule() -> None:
    # spec: anom-009 -- the two rules that produce claims today both have an
    # entry, so the refusal above guards new rules rather than existing ones.
    from app.detection.latency import RECEIVERS_REQUIRED

    assert RECEIVERS_REQUIRED[FAULT] == 1
    assert RECEIVERS_REQUIRED[FUSION] == 2


def test_the_minimum_is_not_a_second_copy_of_the_threshold() -> None:
    # spec: anom-009 -- two copies of a threshold drift, and this drift
    # would move every latency figure at once.
    import inspect

    from app.detection import latency

    source = inspect.getsource(latency)
    assert "DEFAULT_MINIMUM_DURATION" in source
    assert "seconds=10" not in source
