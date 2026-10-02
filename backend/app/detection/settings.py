"""The detector settings every figure of record was measured under. Spec: anom-016.

**These eleven numbers were homeless.** Every detection figure this project quotes
-- the catch rates, the precision, the latencies, the quiet-run bands -- was
measured under one set of detector settings, and until this module that set existed
only in `measurements/corpus/detection_metrics.py` and in a copy in
`tests/test_anom_chain.py` annotated *exactly the policies of record*. `app/` held
none of them, which is harmless exactly as long as nothing inside the application
runs a detector. `anom-016` is the item that does, so a trigger would have had to
declare a third set with the same standing as the other two -- and three copies
that have drifted apart are each internally consistent, so nothing fails: the
screen simply shows figures taken under settings that differ from the ones every
quoted number was measured under. `eval-003` settled the same point at the export
boundary, where *a recorded setting that is not the one in force is worse than
none, because it looks like provenance*; a screen is a second such boundary.

This is `anom-015`'s argument one step along. That item moved the **order** the
rules run in out of a measurement script, for the reason that `measurements/` sits
outside ruff, mypy, pytest and the coverage gate. This moves the **settings** they
run under, and the reason is identical.

**What is homeless is smaller than it looks**, which is most of why nobody noticed.
Four of the six policy objects are taken at their defaults, and those defaults have
always lived here in the package: the sensor-fault rule, the fusion rule, the
precedence ladder and the clustering rule are all `Policy()`. What existed nowhere
in `app/` is `ThresholdPolicy`'s five required fields, `GapPolicy`'s two, and the
corpus box's four coordinates -- eleven values, of which `app/` carried the box
only as an example in a command-line help string.

**Values, not a vocabulary.** The names each setting is *recorded* under are
`eval-003`'s, spelled once in `DetectorPolicies.record`. This module holds only
what they are set to.

The settings themselves are each measured and argued for in their own item --
`anom-001` for the threshold and its severity steps, `anom-014` for the minimum
episode, `anom-010` for the two staleness clocks, `anom-004` and `anom-012` for the
radii. Nothing is chosen here; this is the one place they are written down.
"""

from __future__ import annotations

from datetime import timedelta

from app.detection.baseline import RfMetric
from app.detection.chain import DetectorPolicies
from app.detection.clustering import ClusterPolicy
from app.detection.fusion import FusionPolicy
from app.detection.precedence import PrecedencePolicy
from app.detection.rf_noise import Direction, ThresholdPolicy
from app.detection.sensor_fault import FaultPolicy
from app.detection.track_gap import BoundingBox, GapPolicy

#: How far back `anom-002` measures normal. A setting of record in its own right:
#: `eval-003` requires it beside the thresholds, because the same threshold over a
#: different window is a different detector.
BASELINE_WINDOW: timedelta = timedelta(hours=2)

#: `anom-001`. Power upwards rather than SNR downwards, and the threshold in dB
#: from the baseline mean rather than in multiples of its spread -- which is
#: `anom-003` kept separate on purpose, so the two rules stay independent evidence
#: about one reading rather than one detector counted twice.
RF_POLICY = ThresholdPolicy(
    metric=RfMetric.POWER_DBM,
    direction=Direction.ABOVE,
    threshold=6.0,
    medium_at=10.0,
    high_at=15.0,
)

#: The box the corpus was extracted over. Here rather than in `app/corpus/`
#: because what reads it is a detector: `anom-010`'s interior filter is a
#: correction for having drawn a box at all, and a rule applying it over different
#: bounds than the extract was taken over would discard real aircraft.
CORPUS_BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)

#: `anom-010`. Two clocks, because the two staging mechanisms are different
#: shapes: a frozen position with fresh contact, and no contact at all.
GAP_POLICY = GapPolicy(
    threshold=timedelta(seconds=100),
    contact_fresh_within=timedelta(seconds=30),
    box=CORPUS_BOX,
)

#: What a pass is handed unless a caller is deliberately re-scoring under
#: something else. The parameter exists on every consumer precisely so the same
#: hours can be read under a different threshold -- `eval-001`'s argument for
#: keeping the corpus and the settings separable -- and this is the value that
#: makes a figure on a screen the same figure as a figure in the thesis.
POLICIES_OF_RECORD = DetectorPolicies(
    rf=RF_POLICY,
    fault=FaultPolicy(),
    gap=GAP_POLICY,
    cluster=ClusterPolicy(),
    fusion=FusionPolicy(),
    ladder=PrecedencePolicy(),
)
