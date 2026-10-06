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

**A twelfth setting joined them with `anom-017`: the quiet runs normal is measured
over.** It had been the store's to decide -- every quiet run present when the pass
ran -- so two passes under identical thresholds could disagree, and the store of
record ended up holding findings under two baselines. It is the same argument as the
other eleven, one step along: a setting chosen by the store is not a setting anybody
decided.
"""

from __future__ import annotations

from datetime import timedelta

from app.detection.baseline import RfMetric
from app.detection.chain import DetectorPolicies, PinnedRun
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

#: `anom-017`. The quiet runs `anom-002` measures normal over, **declared rather
#: than discovered**, each with the seed that says which hour it is.
#:
#: Derived on 2026-10-06 from the store of record by
#: `quiet_run_ids` -- every completed `normal-baseline` run, which was exactly
#: these hundred -- and kept as a list because the rule was what moved: run it
#: against a larger store and it returns a different baseline under the same name.
#: All hundred and not the sixty the figures were first measured over, because the
#: sixty are a strict subset and every one of the hundred is corpus v2 by
#: `scn-008`'s base-seed discriminator, 900 s long: one population measured twice,
#: once with forty fewer runs. Five batches of twenty -- the corpus of record's
#: three base seeds and two further ones.
#:
#: To re-derive for another corpus: read the completed quiet runs with their seeds
#: in id order, replace this list, and expect `measure_normality` to refuse until
#: it matches the store it is used against. That refusal is the point.
BASELINE_QUIET_RUNS: tuple[PinnedRun, ...] = (
    # base seed 695081452, runs 21-40
    PinnedRun(21, 166805981),
    PinnedRun(22, 1345373764),
    PinnedRun(23, 1281506699),
    PinnedRun(24, 1046111149),
    PinnedRun(25, 1671112081),
    PinnedRun(26, 1620174491),
    PinnedRun(27, 1297954491),
    PinnedRun(28, 577652087),
    PinnedRun(29, 1274480208),
    PinnedRun(30, 862309905),
    PinnedRun(31, 1434856080),
    PinnedRun(32, 117514344),
    PinnedRun(33, 1787241730),
    PinnedRun(34, 502180977),
    PinnedRun(35, 1430524761),
    PinnedRun(36, 1851510869),
    PinnedRun(37, 1485630712),
    PinnedRun(38, 1374292650),
    PinnedRun(39, 2002992378),
    PinnedRun(40, 293439854),
    # base seed 1412660662, runs 81-100
    PinnedRun(81, 174340479),
    PinnedRun(82, 1875240485),
    PinnedRun(83, 1292162837),
    PinnedRun(84, 1692984457),
    PinnedRun(85, 1948285684),
    PinnedRun(86, 1552594531),
    PinnedRun(87, 1920184254),
    PinnedRun(88, 2108456615),
    PinnedRun(89, 1114381627),
    PinnedRun(90, 1153438802),
    PinnedRun(91, 1680066816),
    PinnedRun(92, 924593934),
    PinnedRun(93, 289235765),
    PinnedRun(94, 748118651),
    PinnedRun(95, 446522131),
    PinnedRun(96, 448328270),
    PinnedRun(97, 1850443630),
    PinnedRun(98, 1861112498),
    PinnedRun(99, 1795779061),
    PinnedRun(100, 540269088),
    # base seed 965530111, runs 181-200
    PinnedRun(181, 1529594995),
    PinnedRun(182, 589895375),
    PinnedRun(183, 272295924),
    PinnedRun(184, 2658869),
    PinnedRun(185, 591477938),
    PinnedRun(186, 2110292449),
    PinnedRun(187, 1717690154),
    PinnedRun(188, 1199985583),
    PinnedRun(189, 563542159),
    PinnedRun(190, 1041545269),
    PinnedRun(191, 678896385),
    PinnedRun(192, 2102849373),
    PinnedRun(193, 1983112751),
    PinnedRun(194, 1040223433),
    PinnedRun(195, 447232922),
    PinnedRun(196, 1453129079),
    PinnedRun(197, 1942973658),
    PinnedRun(198, 1223991610),
    PinnedRun(199, 567595529),
    PinnedRun(200, 1213409055),
    # base seed 655209063, runs 281-300
    PinnedRun(281, 1567394621),
    PinnedRun(282, 103250356),
    PinnedRun(283, 1827244454),
    PinnedRun(284, 394022487),
    PinnedRun(285, 1528599928),
    PinnedRun(286, 461642107),
    PinnedRun(287, 2094756535),
    PinnedRun(288, 1760430909),
    PinnedRun(289, 2034016067),
    PinnedRun(290, 77255740),
    PinnedRun(291, 359231189),
    PinnedRun(292, 1066724417),
    PinnedRun(293, 1117457343),
    PinnedRun(294, 1166592875),
    PinnedRun(295, 1912519329),
    PinnedRun(296, 315208407),
    PinnedRun(297, 495053092),
    PinnedRun(298, 1080982705),
    PinnedRun(299, 1993993051),
    PinnedRun(300, 1352730131),
    # base seed 1284648146, runs 381-400
    PinnedRun(381, 1709575584),
    PinnedRun(382, 155278384),
    PinnedRun(383, 739054506),
    PinnedRun(384, 2137466079),
    PinnedRun(385, 495206081),
    PinnedRun(386, 989043092),
    PinnedRun(387, 350486865),
    PinnedRun(388, 1450184414),
    PinnedRun(389, 1721199379),
    PinnedRun(390, 115533277),
    PinnedRun(391, 676988414),
    PinnedRun(392, 1986404828),
    PinnedRun(393, 1587447171),
    PinnedRun(394, 337385148),
    PinnedRun(395, 290262251),
    PinnedRun(396, 538031510),
    PinnedRun(397, 1082328929),
    PinnedRun(398, 1986626487),
    PinnedRun(399, 745703529),
    PinnedRun(400, 1305389196),
)
