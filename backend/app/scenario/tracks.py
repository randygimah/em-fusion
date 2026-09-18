"""Track perturbation: staging an incident on real replayed data. Spec: scn-002.

The RF side invents readings. This side edits recorded ones, which is a
different kind of act and is why the two live apart. Two of the five scenario
types alter the replayed stream, and they alter it in ways that must stay
distinguishable:

**Only aircraft in flight are staged on** (`scn-006`). The zone test asks
where an aircraft is; it took a measurement to notice it was not also
asking whether the aircraft was flying, and that 55 per cent of every
injection was landing on something parked.

* **`aircraft-coverage-gap` suppresses rows.** The aircraft stops being heard
  from at all, so both staleness clocks run on together. This is what
  `anom-006` should read as a data-source problem.
* **`gnss-degradation` freezes the position clock.** Contact stays fresh -- the
  aircraft is still transmitting -- while the position it reports stops
  advancing. 4,553 rows of the real corpus already carry this shape, so it is a
  real signature rather than an invented one, and it is what `anom-005` should
  read alongside co-located RF noise.

**Where this runs.** Between the adapter and the DAL, and nowhere else.
`adp-001` is a pure windowed reader by specification, so editing rows inside it
would break a passing item; the DAL attaches provenance and validates, so
editing after it would mean rewriting records that have already been stamped.
The replay driver already composes the two, so the seam goes there.

**Selection is keyed, not sampled.** Whether an aircraft is targeted is derived
from the seed and that aircraft's own pseudonym. Nothing depends on arrival
order, on how the replay is batched, or on how many aircraft have been seen so
far -- which matters because the replay is processed one window at a time and a
sampler holding a count would target a different set the moment the window size
changed, while the ground truth went on claiming the first set.

**The freeze is stateless, and that is a deliberate trade.** The obvious
implementation holds each aircraft's last position and re-emits it, which needs
per-aircraft state carried across replay batches and makes the output depend on
the order batches are processed in -- the exact leak `scn-001` closed. Instead
the reported *position staleness* is rewritten to grow with elapsed time inside
the window, which is the field the detectors read and the field the canonical
model documents as the discriminator. The coordinate itself continues to
advance, so a detector that recomputed staleness from successive coordinates
rather than reading the reported value would not see the signature. That is
recorded as a limitation rather than hidden: no rule in Phase 8 does this, and
the alternative costs determinism.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.dal.pseudonymise import Pseudonymiser
from app.scenario.incident import ScenarioType, centre_sensor_id
from app.scenario.layout import RfLayout, great_circle_km
from app.scenario.seeding import derive_unit

if TYPE_CHECKING:  # pragma: no cover -- import cycle, types only
    from app.scenario.emitter import RunSpec


class TrackMode(str, Enum):
    """What a scenario does to the tracks it touches."""

    SUPPRESS = "suppress"
    FREEZE = "freeze"


#: Which type does which. `rf-sensor-fault` is absent on purpose: a faulty
#: receiver says nothing about the aircraft it happens to be listening to, and
#: staging a track effect alongside it would turn a single-cause scenario into
#: one that fires the fusion rule as well.
_MODES: dict[ScenarioType, TrackMode] = {
    ScenarioType.AIRCRAFT_COVERAGE_GAP: TrackMode.SUPPRESS,
    ScenarioType.GNSS_DEGRADATION: TrackMode.FREEZE,
    ScenarioType.AMBIGUOUS_MIXED_EVIDENCE: TrackMode.SUPPRESS,
}

#: The share of the fleet a run touches. Small enough that unaffected traffic
#: remains for the affected traffic to be judged against -- an incident that
#: touched everything would be an outage, and would leave a detector nothing to
#: compare with.
DEFAULT_AFFECTED_FRACTION = 0.08

#: The fewest aircraft a run may stage on (`scn-007`). The fraction above is
#: a share of a pool, and once `scn-006` restricted the pool to aircraft in
#: flight the share began rounding to nothing: a mean of 1.7 per run, with 11
#: of 40 staging none at all and therefore carrying an empty answer key.
#:
#: Measured over 60 seed-matched pairs, grouping each pair by how many
#: aircraft the run actually staged on. Below three, a staged run beats its
#: own control on 16 of 26 pairs -- barely better than a coin. At three,
#: four and five it beats it on **15 of 15**, which at even odds is a one in
#: thirty thousand result. Five is the top of that band and its
#: best-evidenced cell (8 pairs, all won, the largest excess at +2.2
#: findings), so five is taken.
#:
#: The top of the band here, where `anom-014` took the bottom of its
#: plateau, and the asymmetry is deliberate: there every larger value had a
#: measured cost in true episodes, and here a larger value costs nothing and
#: buys margin toward the spread a detector actually has to clear. Five
#: aircraft at the measured yield give roughly two or three detected
#: dropouts, which is the least that can form a zone rather than a pair of
#: points.
#:
#: **What this does not do**, recorded so it is not over-claimed: the
#: control background is 14.4 findings per run with a standard deviation of
#: 3.5, and even the single run that staged twelve aircraft cleared its
#: control by only 4.0 -- about 1.1 standard deviations. No reachable floor
#: makes `anom-006` work by counting findings per run. This removes the
#: empty answer key and gives a zone-level rule something to concentrate;
#: whether that is enough is for re-measurement after the regeneration.
DEFAULT_MINIMUM_AIRCRAFT = 5


@dataclass(frozen=True)
class TrackPerturbation:
    """What a run does to the replayed stream, and when."""

    mode: TrackMode
    start: datetime
    end: datetime
    fraction: float
    seed: int
    centre_lat: float
    centre_lon: float
    radius_km: float

    def covers(self, at: datetime) -> bool:
        return self.start <= at < self.end

    def admits(self, record: Mapping[str, Any]) -> bool:
        """Whether this record is one the run may stage on.

        Window, zone and airborne, in that order. Both the survey
        (`select_targets`) and the perturber ask *this* rather than each
        applying the three gates themselves: a survey that disagreed with
        the perturber about eligibility would rank aircraft the perturber
        then refused, and the answer key would name aircraft nothing was
        done to -- the empty-answer-key failure `scn-007` exists to remove,
        arriving by a different door.
        """
        if not self.covers(record["timestamp"]):
            return False
        location = record.get("location") or {}
        if not self.contains(location.get("lat"), location.get("lon")):
            return False
        # Airborne, or nothing happens (`scn-006`).
        return not record["payload"].get("on_ground")

    def contains(self, lat: float | None, lon: float | None) -> bool:
        """Whether a reported position falls inside the staged zone.

        A record with no position is outside it. Such a row is bound for
        quarantine on the missing coordinate anyway, and inventing a location
        in order to decide whether to perturb it would be inventing data --
        which is the one thing a generator that produces ground truth must not
        do quietly.
        """
        if lat is None or lon is None:
            return False
        return (
            great_circle_km(self.centre_lat, self.centre_lon, lat, lon)
            <= self.radius_km
        )


def plan_track_perturbation(
    layout: RfLayout, spec: RunSpec
) -> TrackPerturbation | None:
    """What this run stages on the tracks, or None when it stages nothing.

    **One centre per run, shared with the RF half.** The zone is derived from
    the seed by the same function `plan_incident` uses, so for the two types
    that stage on both sides the radio anomaly and the track effect are
    co-located by construction rather than by a caller remembering to line them
    up. `anom-005` fuses on co-location in space as well as in time, so two
    independently placed halves would make a scenario's own detectability a
    function of how far apart they happened to land.

    The window is shared for the same reason, and `aircraft-coverage-gap` gets
    a zone of its own despite having no radio incident -- its dropouts have to
    cluster somewhere or `anom-004` has nothing to group.
    """
    scenario_type = ScenarioType(spec.scenario_type)
    mode = _MODES.get(scenario_type)
    if mode is None:
        return None

    centre = layout.site(centre_sensor_id(layout, spec.seed))
    start = spec.start + timedelta(seconds=spec.incident.start_offset_s)
    return TrackPerturbation(
        mode=mode,
        start=start,
        end=start + timedelta(seconds=spec.incident.duration_s),
        fraction=DEFAULT_AFFECTED_FRACTION,
        seed=spec.seed,
        centre_lat=centre.lat,
        centre_lon=centre.lon,
        radius_km=spec.incident.radius_km,
    )


@dataclass(frozen=True)
class TargetSelection:
    """What the survey found, and what it chose from it (`scn-007`)."""

    #: The pseudonyms this run will stage on.
    chosen: frozenset[str]
    #: How many distinct aircraft were eligible at all.
    eligible: int
    #: How many were asked for -- the greater of the floor and the
    #: fraction's expected count.
    requested: int
    #: Whether the pool could supply the floor. False means the run staged
    #: everything it had and still fell short, which is a different fact
    #: from a run that staged few because few were asked for.
    floor_reached: bool


def select_targets(
    perturbation: TrackPerturbation,
    records: Iterable[Mapping[str, Any]],
    *,
    pseudonymiser: Pseudonymiser,
    excluded: frozenset[str] = frozenset(),
    minimum: int = DEFAULT_MINIMUM_AIRCRAFT,
) -> TargetSelection:
    """Survey a run's window and choose what it will stage on.

    **Why this exists as a separate pass.** `scn-002`'s seam is a per-record
    transform over a stream the replay processes one window at a time, so the
    perturber never holds the pool -- which is exactly why selection was made
    a pure function of the seed and one aircraft's pseudonym. A floor cannot
    be expressed that way: "the lowest n" is a statement about a set. So the
    run reads its window once through `adp-001`'s reader without ingesting
    anything, and what comes back is a set rather than a stream.

    **Ranked, not drawn.** Each eligible aircraft keeps the same derived
    value the unbounded rule thresholded on, and the lowest `n` are taken.
    Where the pool is large that is the fraction's own behaviour, because
    taking the lowest 8 per cent by a uniform derivation *is* thresholding at
    0.08; where the pool is small the floor lifts `n` and the same ranking
    answers a bigger question. A draw-until-n loop would have produced the
    count and destroyed the property, since its result depends on the order
    it visited candidates in.

    **Ties broken by pseudonym**, so the ranking is total and two aircraft
    that happened to derive the same value cannot swap between runs.

    A run whose pool cannot supply the floor stages all of it and says so.
    Staging fewer silently would reintroduce the empty answer key this item
    exists to remove.
    """
    if minimum < 0:
        raise ValueError(
            f"the minimum is {minimum}, which is negative. A floor below zero "
            "has no meaning, and clamping it would turn a configuration error "
            "into a run that quietly staged on nothing."
        )

    eligible: set[str] = set()
    for record in records:
        if not perturbation.admits(record):
            continue
        identifier = record["payload"].get("icao24")
        if not identifier:
            continue
        # Excluded before the ranking, never after: an exclusion applied to
        # the result would let the floor pull back in a track `adp-008`
        # removed, which is the confound that list exists to close.
        pseudonym = pseudonymiser.aircraft(str(identifier))
        if pseudonym is None or pseudonym in excluded:
            continue
        eligible.add(pseudonym)

    requested = max(minimum, round(len(eligible) * perturbation.fraction))
    ranked = sorted(
        eligible,
        key=lambda p: (derive_unit(perturbation.seed, "track-target", p), p),
    )
    return TargetSelection(
        chosen=frozenset(ranked[:requested]),
        eligible=len(eligible),
        requested=requested,
        floor_reached=len(eligible) >= minimum,
    )


class TrackPerturber:
    """Applies one run's track perturbation, record by record.

    Stateful in exactly one respect -- it remembers which aircraft it has
    actually touched, so the ground truth can name them -- and that state never
    influences a decision. Whether an aircraft is targeted is a pure function of
    the seed and its pseudonym, so the set is the same however the stream is
    ordered or batched.
    """

    def __init__(
        self,
        perturbation: TrackPerturbation,
        *,
        pseudonymiser: Pseudonymiser,
        excluded: frozenset[str] = frozenset(),
        selection: TargetSelection | None = None,
    ) -> None:
        self._perturbation = perturbation
        self._pseudonymiser = pseudonymiser
        self._excluded = excluded
        self._selection = selection
        self._affected: set[str] = set()

    @property
    def mode(self) -> TrackMode:
        return self._perturbation.mode

    @property
    def selection(self) -> TargetSelection | None:
        """What the survey chose, when one was run (`scn-007`).

        None means no survey: the perturber is applying the fraction alone
        with no floor, which is what it did before `scn-007` and remains an
        honest description rather than a fallback pretending to be the rule.
        """
        return self._selection

    @property
    def affected(self) -> frozenset[str]:
        """The pseudonyms this run actually touched, for the ground truth.

        Collected rather than predicted, because which targeted aircraft
        appear in the window at all is a property of the corpus, not of the
        seed. An answer key naming aircraft that never showed up would report
        misses the detector had no chance to find.
        """
        return frozenset(self._affected)

    def targets(self, icao24: str) -> bool:
        """Whether this run stages anything on this aircraft.

        Excluded tracks are refused before the draw rather than after, so the
        exclusion cannot be undone by a later change to how selection works
        (`adp-008`).

        With a survey (`scn-007`) the answer is membership of the set it
        chose, which already applied the same exclusion over the same pool.
        Without one it is the unbounded fraction.
        """
        pseudonym = self._pseudonymiser.aircraft(icao24)
        if pseudonym is None or pseudonym in self._excluded:
            return False
        if self._selection is not None:
            return pseudonym in self._selection.chosen
        return (
            derive_unit(self._perturbation.seed, "track-target", pseudonym)
            < self._perturbation.fraction
        )

    def apply(self, record: Mapping[str, Any]) -> dict[str, Any] | None:
        """One source record in; the perturbed record, or None if suppressed.

        Returns the record unchanged -- the same object's contents -- whenever
        nothing applies, so a run that stages nothing costs nothing and cannot
        alter a stream by accident.
        """
        timestamp = record["timestamp"]
        # Airborne, or nothing happens. Spec: scn-006. This gate sits *above*
        # the answer key rather than beside the metrics, and the placement is
        # the whole point: a parked aircraft that were merely excused later
        # would still carry a perturbed record that no ground truth names.
        #
        # Measured before this existed: of 381 aircraft the key called staged,
        # 209 were on the ground for every report of the run. The zone test
        # asks where an aircraft is and nothing else, so one parked at an
        # airfield inside the zone was targeted like one flying through it --
        # and `anom-010` then refused it, correctly, because an aircraft on the
        # ground stopped reporting when it was switched off. Two components
        # each behaving as specified, combining into a guaranteed false
        # negative.
        #
        # Per record, not per aircraft: one that takes off inside the window is
        # eligible for the part it was flying, and excluding it wholesale would
        # trade one bias for another.
        #
        # Window, zone and airborne are asked of the perturbation itself, so
        # the survey in `select_targets` cannot drift from what happens here.
        if not self._perturbation.admits(record):
            return dict(record)

        identifier = record["payload"].get("icao24")
        if not identifier or not self.targets(str(identifier)):
            return dict(record)

        pseudonym = self._pseudonymiser.aircraft(str(identifier))
        if pseudonym is not None:
            self._affected.add(pseudonym)

        if self._perturbation.mode is TrackMode.SUPPRESS:
            return None

        # FREEZE. The position stopped advancing when the window opened, so its
        # age is however long the window has been running plus whatever it
        # already was. Contact is untouched: the aircraft is still transmitting,
        # and that is the entire difference from a coverage gap.
        elapsed = (timestamp - self._perturbation.start).total_seconds()
        perturbed = dict(record)
        payload = dict(record["payload"])
        payload["position_staleness_s"] = round(
            float(payload["position_staleness_s"]) + elapsed, 2
        )
        perturbed["payload"] = payload
        return perturbed


def load_exclusions(path: Path) -> frozenset[str]:
    """The aircraft `adp-008` says must never be staged on.

    Raises rather than returning an empty set when the file is absent. An empty
    set is the answer "no track carries a natural gap", and a missing file is
    the answer "nobody looked" -- and the two are indistinguishable to a caller
    that gets an empty set for both, which would let the mitigation silently
    stop applying.

    Tracks, not gaps: an aircraft carrying two natural gaps is one aircraft to
    exclude, and conflating the two is what put the confound at 1.05% instead
    of 0.74%.
    """
    document = json.loads(Path(path).read_text())
    return frozenset(gap["aircraft_id"] for gap in document["gaps"])
