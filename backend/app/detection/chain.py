"""The detection pass over one completed run. Spec: anom-015.

**This composes and does not decide.** Every rule keeps its own logic and is
called rather than reimplemented; what lives here is the order they run in, which
is `anom-013`'s ladder plus the wiring between one rule's output and the next
one's input.

The argument for it being a module at all is that the ordering existed only
inside `measurements/corpus/detection_metrics.py` -- baselines, RF episodes,
faults, gaps, clusters, fusion, then the ladder -- and `measurements/` sits
deliberately outside `make lint`, `make type-check`, `make test` and the coverage
gate. So the composition producing every detection figure this project quotes was
the one part of the chain nothing checked, while all eight rules sat at 100%
individually. `ai-011` exists because by the time five parts worked separately,
three ways of joining them produced a system that ran perfectly and reported
something false; this is its counterpart, and the detection layer had none.

**Normality is an input, not something this can compute.** `anom-002` measures
mean and spread per sensor per channel over the corpus's *quiet* runs across a
trailing window -- sixty of them, here -- and not over the run being scored. A
pass that rebuilt a baseline from its own run would measure the injected incident
as normal and report the arm clean, which is worse than refusing because it looks
like a detection result. So a store with no quiet runs is refused, and `Normality`
carries the runs it was measured over for the same reason the policy record does.

**Persisting is load-bearing mid-chain.** `anom-004` and `anom-012` are PostGIS
queries over stored rows, so the track findings are written *before* those rules
run. Compute-then-store is not an available shape: a pass written that way finds
no track evidence and reports it absent rather than unwritten, which is a wrong
answer that looks like a quiet corpus.

**What it stores, and the line it draws.** It persists findings through `db-008`,
replacing per run per rule, and it **builds but does not store** the evidence
bundles. The line is between what is regenerable and id-free and what carries
identity something else cites: a finding is derived, replaced wholesale and
referred to by nothing, while `eval-004`'s pre-registered sample names its twenty
bundles **by id**. A pass that rebuilt bundles corpus-wide would renumber that
population and stop the draw reproducing itself -- so storing them is a decision
with pre-registration consequences, which makes it the caller's and not this
module's. `ai-011` draws the same line for the same reason: it assembles and does
not run.

It invents no third representation either way: the `anomalies` table has existed
since `0001` and nothing has ever written to it, while `evb-001`'s
one-bundle-per-reported-claim is already the established unit. That table is
recorded as dead rather than quietly adopted.

**It is idempotent**, which `db-008`'s replace semantics give for free and which
matters more than it sounds: resolution of a bundle's citations happens in full
before anything is written (`evb-002`), but the track findings are already down by
then, so a pass that fails late leaves findings and no bundles. Running it again
is the whole recovery, and nothing has to be cleared up first.

**Not pure, and cannot be.** Two of the rules it composes are database queries, so
a session factory is a parameter.

**It reads its own observations, and that was a correction.** The first version
took them as values, which the suite rejected for a reason worth keeping: the
bundles this stores are resolved against *stored* observations (`evb-002`), so the
values the rules reason from and the rows the citations resolve against have to be
the same thing. Taking them as parameters makes `assess(run 7, observations of run
9)` representable, and the only thing that catches it is a citation resolution at
the very end -- by which point run 7's findings have already been written from run
9's data. A partial wrong write, not a loud refusal. Reading them here through
`db/repository.observations_for_run` makes the mismatch unrepresentable, puts the
SQL where `FR-904` wants it, and replaces the hand-rolled reader both measurement
scripts grew, each inventing five fields the row already holds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

from app.dal.models import ObservationType, ScenarioRunSummary
from app.db.bundles import save_bundles
from app.db.findings import save_findings
from app.db.repository import observations_for_run, record_detection_pass
from app.detection.baseline import BaselineTable, compute_rf_baselines
from app.detection.bundle import EvidenceBundle, build_bundles
from app.detection.clustering import FINDING_TYPE as CLUSTER_TYPE
from app.detection.clustering import RULE_ID as CLUSTER_RULE
from app.detection.clustering import (
    ClusterPolicy,
    TrackGapCluster,
    cluster_track_gaps,
)
from app.detection.findings import (
    DetectionFinding,
    from_interference_zone,
    from_rf_noise,
    from_sensor_fault,
    from_track_gap,
)
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE_TYPE
from app.detection.fusion import RULE_ID as FUSION_RULE
from app.detection.fusion import (
    FusionPolicy,
    InterferenceFindings,
    claims_from_interference,
    detect_interference,
)
from app.detection.precedence import (
    Claim,
    PrecedencePolicy,
    Resolution,
    claims_from_sensor_faults,
    resolve,
)
from app.detection.rate_excess import FINDING_TYPE as EXCESS_TYPE
from app.detection.rf_noise import ANOMALY_TYPE as RF_TYPE
from app.detection.rf_noise import (
    DEFAULT_MINIMUM_DURATION,
    RfNoiseFindings,
    ThresholdPolicy,
    detect_rf_noise,
)
from app.detection.rf_noise import RULE_ID as RF_RULE
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT_TYPE
from app.detection.sensor_fault import RULE_ID as FAULT_RULE
from app.detection.sensor_fault import (
    FaultPolicy,
    SensorFaultFindings,
    detect_sensor_faults,
)
from app.detection.track_gap import FINDING_TYPE as GAP_TYPE
from app.detection.track_gap import RULE_ID as GAP_RULE
from app.detection.track_gap import GapPolicy, detect_track_gaps
from app.scenario.layout import RfLayout

Key = tuple[str, str]


class ChainError(ValueError):
    """A run this pass refuses to score, or a baseline it refuses to hold."""


@dataclass(frozen=True, slots=True)
class Normality:
    """What normal is, and what it was measured over. Spec: anom-015, anom-002.

    The second half is not bookkeeping. Two passes under identical thresholds and
    different baselines produce different findings, and recorded without the runs
    they are indistinguishable -- which defeats recording the policy at all.
    """

    table: BaselineTable
    quiet_run_ids: tuple[int, ...]
    window: timedelta

    def __post_init__(self) -> None:
        if not self.quiet_run_ids:
            raise ChainError(
                "a baseline measured over no quiet runs: normality is measured "
                "over the corpus's quiet runs and not over the run being scored, "
                "so a store holding none cannot be scored at all. Generating one "
                "batch of staged runs into an empty database is the case this "
                "refuses, and the alternative -- baselining against staged data -- "
                "would measure the incident as normal and report the arm clean."
            )


@dataclass(frozen=True, slots=True)
class DetectorPolicies:
    """Every setting the pass reads a run through. Spec: anom-015, eval-003.

    One object because a pass must record them all together: `eval-003` refuses a
    provenance record missing one of `REQUIRED_POLICIES`, and a record assembled
    field by field at the call site is a second place for the vocabulary to live.
    """

    rf: ThresholdPolicy
    fault: FaultPolicy
    gap: GapPolicy
    cluster: ClusterPolicy
    fusion: FusionPolicy
    ladder: PrecedencePolicy

    def record(self, normality: Normality, *, layout: RfLayout) -> dict[str, str]:
        """The settings as `eval-003` spells them, plus the baseline's own runs.

        `eval-003`'s names verbatim rather than a second spelling, so a pass's
        provenance satisfies the export's floor by construction and the two
        cannot drift into disagreeing about the same threshold.
        """
        from app.detection.rate_excess import DEFAULT_RADIUS_KM as EXCESS_RADIUS_KM

        # A policy with no box applies no interior filter, which is a setting
        # rather than a gap in the record -- so it is written as such. Crashing
        # here would make a legitimate policy unrecordable; omitting the key would
        # fail `eval-003`'s floor at the export instead.
        box = self.gap.box
        bounds = (
            "none"
            if box is None
            else f"{box.lat_min},{box.lat_max},{box.lon_min},{box.lon_max}"
        )
        excess_radius = (
            EXCESS_RADIUS_KM
            if self.fusion.excess_radius_km is None
            else self.fusion.excess_radius_km
        )
        return {
            # what "normal" is measured over
            "BASELINE.window_h": str(normality.window.total_seconds() / 3600),
            "BASELINE.quiet_runs": ",".join(str(i) for i in normality.quiet_run_ids),
            "BASELINE.quiet_run_count": str(len(normality.quiet_run_ids)),
            # the radio rule
            "RF-NOISE.metric": self.rf.metric.value,
            "RF-NOISE.direction": self.rf.direction.value,
            "RF-NOISE.threshold_db": str(self.rf.threshold),
            "RF-NOISE.medium_at_db": str(self.rf.medium_at),
            "RF-NOISE.high_at_db": str(self.rf.high_at),
            "RF-NOISE.minimum_episode_s": str(DEFAULT_MINIMUM_DURATION.total_seconds()),
            # the aircraft side
            "TRACK-GAP.threshold_s": str(self.gap.threshold.total_seconds()),
            "TRACK-GAP.contact_fresh_within_s": str(
                self.gap.contact_fresh_within.total_seconds()
            ),
            "TRACK-GAP.box": bounds,
            "TRACK-GAP.rate_excess_radius_km": str(EXCESS_RADIUS_KM),
            "TRACK-CLUSTER.radius_km": str(self.cluster.radius_km),
            # the rules that reason about other rules
            "SENSOR-FAULT.neighbour_radius_km": str(self.fault.radius_for(layout)),
            "FUSION-SPATIAL.corroboration_threshold": str(
                self.fusion.corroboration_threshold
            ),
            "FUSION-SPATIAL.excess_radius_km": str(excess_radius),
        }


@dataclass(frozen=True, slots=True)
class Bid:
    """One rule's claim and the receivers whose evidence it rested on.

    Kept because `anom-009` needs them and no claim carries them: the rules
    retain derived evidence on purpose, so a `SensorFault` cannot say when its own
    evidence matured, and the registry that computes latency states a **count of
    receivers** rather than a formula. `anom-005`'s zone window is the *union* of
    its receivers', so `window start + minimum` is right for a fault and wrong for
    interference, where only the first receiver has begun at the union's start.

    The pass is the only place both halves are in view at once, which is the same
    argument `ai-011` makes for naming the arm once.
    """

    claim: Claim
    sensors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Assessment:
    """Everything one pass produced, and the settings it produced them under."""

    scenario_run_id: int
    rf: RfNoiseFindings
    faults: SensorFaultFindings
    gaps: tuple[DetectionFinding, ...]
    clusters: tuple[TrackGapCluster, ...]
    interference: InterferenceFindings
    resolution: Resolution
    bids: tuple[Bid, ...]
    bundles: tuple[EvidenceBundle, ...]
    policy: Mapping[str, str]

    def receivers_for(self, claim: Claim) -> tuple[str, ...]:
        """The receivers behind one claim, or a refusal.

        Matched on **identity**: the ladder passes claims through unchanged, so the
        object reported is the object bid. Equality would conflate two claims a
        run legitimately holds -- `anom-013` suppresses within a zone and a run may
        carry several of one rule's claims.

        A claim this does not know raises rather than returning nothing, on
        `anom-009`'s own rule that an undeclared rule is refused: an empty tuple
        would make the latency of an interference zone the latency of its first
        receiver, silently understating it by however long they were staggered.
        """
        for bid in self.bids:
            if bid.claim is claim:
                return bid.sensors
        raise ChainError(
            f"no receivers recorded for a {claim.rule_id} claim: this pass did not "
            "produce it, and returning none would let anom-009 measure a zone's "
            "latency from whichever receiver happened to begin first."
        )

    @property
    def reported(self) -> tuple[Claim, ...]:
        """The claims that reached an analyst, after `anom-013` suppressed."""
        return tuple(self.resolution.reported)

    @property
    def counts(self) -> dict[Key, int]:
        """One entry per built producer, keyed as `anom-008` keys its register.

        The account that control grades a quiet run against, and it must be
        complete: detectors that ran and found nothing, detectors that never ran
        and detectors pointed at the wrong observations all produce an identical
        empty result, so a producer missing from here makes the control
        unanswerable rather than wrong. Keyed on the `(rule_id, finding_type)`
        pair because `anom-012` borrows `anom-010`'s rule id.
        """
        types = [claim.anomaly_type for claim in self.reported]
        return {
            (RF_RULE, RF_TYPE): len(self.rf.anomalies),
            (GAP_RULE, GAP_TYPE): len(self.gaps),
            (CLUSTER_RULE, CLUSTER_TYPE): len(self.clusters),
            (GAP_RULE, EXCESS_TYPE): len(self.interference.zones)
            + len(self.interference.declined),
            (FAULT_RULE, FAULT_TYPE): sum(1 for t in types if t == FAULT_TYPE),
            (FUSION_RULE, INTERFERENCE_TYPE): sum(
                1 for t in types if t == INTERFERENCE_TYPE
            ),
        }


def measure_normality(
    session_factory: object,
    *,
    quiet_run_ids: Sequence[int],
    policies: DetectorPolicies,
    window: timedelta,
) -> Normality:
    """What normal is, measured over the store's quiet runs. Spec: anom-016.

    Here rather than at the call site because of one thing a call site gets wrong
    silently: **the metric is declared twice**. A baseline is built over one
    metric and `anom-001` reads its deviation against another, and the script this
    replaces named `RfMetric.POWER_DBM` once when building the table and again on
    the policy. Disagree and every threshold is measured in the wrong units with
    nothing failing, because both halves are individually valid. Taken from
    `policies.rf.metric` here, so they cannot differ.

    **The runs are the caller's choice and arrive as ids.** Which runs count as
    quiet is answered by the scenario type, which is the label for what was
    injected -- the one thing `api-009` keeps out of an observation. So the
    selection happens outside the detection layer and what crosses into it is a
    list of numbers, exactly as `anom-008` requires of its own caller.

    **It refuses an empty list itself**, which was a correction. Two refusals of
    that condition already exist upstream -- `compute_rf_baselines` will not take
    an empty allowlist and `Normality` will not hold an empty provenance -- so this
    looked like a third. It is not the same statement: the one that actually fires
    first is the baseline's, and it talks about an *allowlist* an engine cannot
    widen, while the fact a caller needs is that **this store holds no quiet runs
    at all**, which is what a freshly generated database always looks like. A
    refusal whose message is about the wrong thing is how a trigger reports a fresh
    database as a detector defect. Decided before any read, because there is
    nothing to read.
    """
    ids = tuple(quiet_run_ids)
    if not ids:
        raise ChainError(
            "no quiet runs in the store: normality is measured over the quiet "
            "runs and never over the run being scored, so there is nothing here "
            "to measure it over. A batch generated into an empty database is "
            "exactly this case, and the alternative -- baselining against the "
            "staged runs -- would measure the injected incident as normal and "
            "report every arm clean."
        )
    observations = [
        observation
        for run_id in ids
        for observation in observations_for_run(
            session_factory,  # type: ignore[arg-type]
            run_id,
            ObservationType.RF,
        )
    ]
    return Normality(
        table=compute_rf_baselines(
            observations,
            policies.rf.metric,
            baseline_run_ids=ids,
            window=window,
        ),
        quiet_run_ids=ids,
        window=window,
    )


def reported_findings(
    resolution: Resolution,
    *,
    evidence: Sequence[tuple[Claim, DetectionFinding]],
) -> tuple[DetectionFinding, ...]:
    """The findings for the claims `anom-013` reported, and no others.

    Pure, and separated from the write for the reason the write cannot be: the
    decision is "which conclusions reached the analyst", which is checkable with
    two constructed claims, while the write needs a database and a whole run to
    stage a contest in.

    **A suppressed claim is never written.** It is a *competing conclusion* and
    not a second event -- `evb-001` carries one in `superseded` and never in the
    evidence list, precisely so that co-occurrence is not read as concurrence --
    and stored beside the claim that beat it, every count over the table reads
    two events where there was one.

    Matched on **identity**, as `Assessment.receivers_for` is and for the same
    reason sharpened: a `Claim` is a frozen dataclass of a rule id, a type and a
    zone, so two claims of one rule over one zone are *equal*. A membership test
    would write the finding of a claim the ladder never reported. The ladder
    passes claims through unchanged, so the object reported is the object bid.
    """
    reported = resolution.reported
    return tuple(
        finding for claim, finding in evidence if any(claim is won for won in reported)
    )


def assess(
    run: ScenarioRunSummary,
    *,
    normality: Normality,
    policies: DetectorPolicies,
    layout: RfLayout,
    session_factory: object,
) -> Assessment:
    """Run every rule over one finished run, store what they found, report it.

    Takes the run's **summary** rather than its id, because the completion stamp
    is part of the decision: `db-007` records absence of one as *not known to have
    finished*, covering a run still going and a run that died, and scoring either
    gives findings over partial observations that change when the run completes.

    Neither refusal can leave a partial write behind. The completion check is
    decided from the summary alone, before the database is touched at all; the
    empty-run check can only be made after reading, since that is what establishes
    it, but it still precedes every write.
    """
    if run.completed_at is None:
        raise ChainError(
            f"run {run.id} is not known to have finished: db-007 records the "
            "absence of a completion stamp as exactly that, which covers a run "
            "still going and a run that died. Findings over partial observations "
            "change when the run completes, so a figure read from them would not "
            "be the figure the run produces."
        )

    rf = observations_for_run(
        session_factory,  # type: ignore[arg-type]
        run.id,
        ObservationType.RF,
    )
    tracks = observations_for_run(
        session_factory,  # type: ignore[arg-type]
        run.id,
        ObservationType.TRACK,
    )
    if not rf:
        raise ChainError(
            f"run {run.id} has no RF observations: the run's span is taken from "
            "its readings and every rule after the first is scoped to that span, "
            "so a pass here would report a run nothing was measured on as a run "
            "where nothing was found."
        )

    policy = policies.record(normality, layout=layout)
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))

    # The radio side first: `anom-007` reads `anom-001`'s episodes to judge the
    # *shape* of an abnormality and measures no readings of its own.
    episodes = detect_rf_noise(rf, normality.table, policies.rf)
    faults = detect_sensor_faults(episodes, rf, normality.table, layout, policies.fault)

    # The aircraft side, written down **before** the two rules that query it.
    gaps = tuple(
        from_track_gap(gap, scenario_run_id=run.id)
        for gap in detect_track_gaps(tracks, policies.gap)
    )
    save_findings(
        session_factory,  # type: ignore[arg-type]
        scenario_run_id=run.id,
        rule_id=GAP_RULE,
        findings=gaps,
        policy=policy,
    )
    save_findings(
        session_factory,  # type: ignore[arg-type]
        scenario_run_id=run.id,
        rule_id=RF_RULE,
        findings=[
            from_rf_noise(anomaly, scenario_run_id=run.id)
            for anomaly in episodes.anomalies
        ],
        policy=policy,
    )

    # Now the rules that read those rows. `anom-004`'s clusters are not persisted:
    # `from_track_cluster` is a declared non-resolver -- its ref is an aircraft id
    # with no time, which matches many rows rather than one -- so storing them
    # would put citations `evb-002` refuses by name into the store for no reader.
    clusters = tuple(
        cluster_track_gaps(
            session_factory,  # type: ignore[arg-type]
            scenario_run_id=run.id,
            window=span,
            policy=policies.cluster,
        )
    )
    interference = detect_interference(
        faults,
        session_factory,  # type: ignore[arg-type]
        scenario_run_id=run.id,
        run_span=span,
        layout=layout,
        policy=policies.fusion,
    )

    # One bid per rule, sorted by a declared constant, and a zone an earlier rule
    # claimed is never offered to a later one (`anom-013`). The two producers emit
    # in finding order, so the receivers pair positionally rather than being
    # looked up -- and they are kept, because nothing downstream can recover them.
    fault_claims = claims_from_sensor_faults(faults, layout)
    zone_claims = claims_from_interference(interference)
    bids = (
        *(
            Bid(claim=claim, sensors=(fault.sensor_id,))
            for claim, fault in zip(fault_claims, faults.faults, strict=True)
        ),
        *(
            Bid(claim=claim, sensors=tuple(zone.sensors))
            for claim, zone in zip(zone_claims, interference.zones, strict=True)
        ),
    )
    resolution = resolve([*fault_claims, *zone_claims], layout, policies.ladder)

    # The conclusions, written down. Until `anom-015`'s second amendment they
    # were not: only the rules something later *queries* had rows, so from any
    # other process the two claims this whole chain exists to produce did not
    # exist. Per rule, because `db-008` replaces per run per rule -- and both
    # calls happen whether or not either rule claimed anything, since the
    # replace at zero is what clears a previous pass's rows.
    conclusions = reported_findings(
        resolution,
        evidence=(
            *(
                (claim, from_sensor_fault(fault, scenario_run_id=run.id))
                for claim, fault in zip(fault_claims, faults.faults, strict=True)
            ),
            *(
                (claim, from_interference_zone(zone, scenario_run_id=run.id))
                for claim, zone in zip(zone_claims, interference.zones, strict=True)
            ),
        ),
    )
    # **Built and now stored** (`evb-003`). The module docstring recorded the
    # opposite, and the reason it gave was sound and narrower than the
    # behaviour it bought: `eval-004`'s pre-registered sample names twenty
    # bundles by id, so a pass rebuilding them corpus-wide renumbers that
    # population -- which protects twenty bundles on twenty runs and was
    # implemented as *store none, ever*. `db-011` makes that protection
    # structural and decided from the store, after which storing is safe for
    # every run nothing cites: 380 of 400.
    bundles = build_bundles(
        resolution,
        scenario_run_id=run.id,
        faults=faults.faults,
        zones=interference.zones,
        rf=episodes,
        track_findings=gaps,
    )

    # **First of the three writes**, and the order is the decision (`evb-003`).
    # This is the only one that can REFUSE -- `db-011` protects a bundle a
    # hypothesis cites, because the write replaces per run and the citation is
    # declared ON DELETE CASCADE -- so a protected run leaves the store as it
    # was. Written last, a refusal would end the pass with this hour's
    # conclusions standing beside the previous hour's evidence, and no property
    # of either row could detect the disagreement.
    #
    # Not total, and the limit is worth stating: the track findings above were
    # written before the rules that read them back ran, so a refusal still
    # leaves those replaced. Harmlessly -- that write is idempotent and happens
    # on every pass -- but it is a partial write and saying otherwise would be
    # the overclaim.
    #
    # There is no ordering dependency on the findings write at all. `evb-002`
    # resolves every citation against **observations**, which are written at
    # generation time, so a bundle written first cites rows that have been
    # there since the run was made.
    save_bundles(session_factory, scenario_run_id=run.id, bundles=bundles)  # type: ignore[arg-type]

    # Written out rather than looped, and the reason is a test: `api-012`
    # declares which producers this pass persists, and the only honest way to
    # hold that declaration to the pass is to read the rule ids off these calls.
    # A loop variable hides them from a reader of this module as well.
    save_findings(
        session_factory,  # type: ignore[arg-type]
        scenario_run_id=run.id,
        rule_id=FAULT_RULE,
        findings=[f for f in conclusions if f.rule_id == FAULT_RULE],
        policy=policy,
    )
    save_findings(
        session_factory,  # type: ignore[arg-type]
        scenario_run_id=run.id,
        rule_id=FUSION_RULE,
        findings=[f for f in conclusions if f.rule_id == FUSION_RULE],
        policy=policy,
    )

    # **Last**, after every write. A pass that dies midway then leaves a run
    # that is not known to have been scored, rather than one claiming an
    # examination it did not finish -- and `db-008`'s replace semantics make
    # running it again the whole recovery. Stamped first, a crash would leave a
    # complete-looking record over a partial set of findings, which nothing can
    # detect from either side.
    #
    # Written whether or not anything was found, which is the point of it: the
    # findings write replaces per run per rule *including at zero*, so a run
    # examined and found clean leaves exactly what a run nobody examined leaves.
    # This is the only thing that tells the two apart (`anom-008`, `api-012`).
    record_detection_pass(
        session_factory,  # type: ignore[arg-type]
        run.id,
        policy=policy,
    )
    return Assessment(
        scenario_run_id=run.id,
        rf=episodes,
        faults=faults,
        gaps=gaps,
        clusters=clusters,
        interference=interference,
        resolution=resolution,
        bids=bids,
        bundles=bundles,
        policy=policy,
    )
