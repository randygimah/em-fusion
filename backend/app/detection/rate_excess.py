"""Local discontinuity rate excess. Spec: anom-012.

The track side's contribution to fusion, and it replaces cluster size
because cluster size carries no signal: over 40 matched pairs the largest
cluster on a staged run beats its own control in one to three, at every
radius from 5 to 60 km.

**The question changed rather than the scenario settings.** Instead of "is
there a large group here", judged against a standard the background already
meets, this asks *at this place, are discontinuities more frequent during
this window than at the same place outside it*. The comparison is internal
to one run and one location, which controls for the two things that
defeated clustering: air traffic is not uniform, so a busy place is always
busy, and runs differ from one another. Nothing here is calibrated against
another run.

Measured, pooled over 40 matched pairs from two independently seeded
batches, with the second scored at thresholds the first chose rather than
refitted: 16 of 40 staged against 7 of 40 controls at 30 km, 23 against 10
at 45 km, 31 against 15 at 60 km, for Fisher's exact of 0.047, 0.006 and
0.001. Real at every radius, and weak -- a Youden's J of 0.23 to 0.40 on a
scale where zero is a coin flip. `anom-001`'s radio side separates 8 dB
from a 1.5 dB spread, beyond five sigma, and `anom-013` exists because
asking the weaker signal to arbitrate what the stronger one settles was the
error that produced a 70 per cent misattribution rate.

**No threshold lives here.** Which point of that curve is right depends on
`anom-013`'s ordering and on `anom-007`'s catch rate, neither of which
exists yet, so the number is computed and the meaning is decided by the
consuming rule where it can be seen.

The disc is selected with `db-004` rather than by measuring distance in
this module, because a second copy of the distance rule is the trap this
repository has recorded once already.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.dal.models import Location
from app.db.findings import findings_near
from app.detection.track_gap import RULE_ID as SOURCE_RULE_ID

FINDING_TYPE = "track_rate_excess"

#: How wide a patch to measure over, in kilometres.
#:
#: This item shipped without a default, deliberately: the three measured
#: radii were three different trades between a missed incident and a
#: misattributed one, and a default would have made that choice quietly.
#: That argument is discharged rather than overturned. `anom-007` claims
#: every sensor-fault run, so the only runs reaching a fusion decision are
#: the interference ones -- 40 of 40 gnss-degradation against 0 of 40
#: aircraft-coverage-gap and 1 of 40 rf-sensor-fault -- and with no
#: false-positive pressure at that step the curve is read at its sensitive
#: end, which is what `anom-013` predicted from the ordering.
#:
#: The second reason needs no measurement: 60 km is `scn-002`'s own
#: configured incident radius, so the disc matches the scale of the zone it
#: measures. That is configuration rather than per-run ground truth, and it
#: is the basis `anom-004` used for its own default.
DEFAULT_RADIUS_KM = 60.0


@dataclass(frozen=True, slots=True)
class ExcessPolicy:
    """How wide a patch to measure over.

    Defaults to `DEFAULT_RADIUS_KM`, which carries the reasoning. The
    number is still a choice and still reversible; what changed is that it
    has been made in the open rather than left to each call site.
    """

    radius_km: float = DEFAULT_RADIUS_KM

    def __post_init__(self) -> None:
        if self.radius_km <= 0:
            raise ValueError(f"radius_km={self.radius_km} must be positive")


@dataclass(frozen=True, slots=True)
class RateExcess:
    """How much busier a place was during a window than outside it.

    No severity, no threshold, no confidence: this is a measurement and
    `anom-005` is where it becomes a judgement. The same structural
    argument `anom-004` and `anom-010` make, and asserted the same way.
    """

    centre: Location
    radius_km: float
    window: tuple[datetime, datetime]
    during: int
    outside: int
    during_per_minute: float
    outside_per_minute: float
    #: The smoothed ratio of the two rates, which is the quantity every
    #: figure in the docstring above was measured on.
    ratio: float

    @property
    def excess(self) -> float:
        """How far above the local baseline, so nothing at all reads zero."""
        return self.ratio - 1.0


#: One finding per run, spread across the whole run, added to both rates.
#: Without it a window holding findings and a remainder holding none gives
#: an infinite ratio, which no threshold can order against a finite one.
#: The measured figures in this module's docstring were taken with exactly
#: this smoothing, so changing it invalidates them.
def _rate(count: int, seconds: float, span_seconds: float) -> float:
    return count / seconds + 1.0 / span_seconds


def measure_rate_excess(
    session_factory: sessionmaker[Session],
    *,
    scenario_run_id: int,
    centre: Location,
    policy: ExcessPolicy,
    window: tuple[datetime, datetime],
    run_span: tuple[datetime, datetime],
) -> RateExcess:
    """The rate inside a disc during a window, against the same disc outside it.

    `window` and `centre` come from `anom-007`'s assessment of a zone and
    never from ground truth: an observation carries no scenario type for
    the engine to recognise staged data by (`api-009`), and this rule must
    not be the place that changes.

    **From the assessment, and not from an `anom-001` episode directly.**
    An episode is not an incident: the injected elevation dips below that
    rule's threshold about one tick in six, so one 300 s incident arrives
    as a median of six episodes, and the longest of them has a median
    length of 90 s. `anom-007`'s window is seeded by those episodes and
    bounded by the readings, and recovers the incident at a median of
    320 s. That matters more here than anywhere else, because the window
    and its complement are the two halves of the ratio -- a window a third
    of the true length puts two thirds of the incident's own findings into
    the reference period they are being compared against.

    A rate and not a count, because the window and its complement have
    different durations -- on the generator's own numbers, 300 s against
    600 s, so equal counts are twice the rate inside and a count would
    report no excess where there is one.
    """
    window_s = (window[1] - window[0]).total_seconds()
    span_s = (run_span[1] - run_span[0]).total_seconds()
    outside_s = span_s - window_s
    if window_s <= 0:
        raise ValueError(
            "the window has no length, so there is no period to measure a rate "
            "over. A single-reading RF episode has its start equal to its end "
            "and 6 of 86 staged runs produce one; clamping it would return a "
            "number computed over one reading with nothing to mark it as "
            "different from a measurement."
        )
    if outside_s <= 0:
        raise ValueError(
            "the window covers the whole run, so there is no reference period "
            "to compare it against. An excess measured against an empty "
            "remainder is a property of the window, not of the place."
        )

    in_disc = findings_near(
        session_factory,
        scenario_run_id=scenario_run_id,
        centre=centre,
        radius_km=policy.radius_km,
        window=run_span,
        rule_id=SOURCE_RULE_ID,
    )
    during = sum(
        1 for f in in_disc if f.started_at < window[1] and f.ended_at > window[0]
    )
    outside = len(in_disc) - during

    during_rate = _rate(during, window_s, span_s)
    outside_rate = _rate(outside, outside_s, span_s)

    return RateExcess(
        centre=centre,
        radius_km=policy.radius_km,
        window=window,
        during=during,
        outside=outside,
        during_per_minute=during / window_s * 60.0,
        outside_per_minute=outside / outside_s * 60.0,
        ratio=during_rate / outside_rate,
    )
