"""How well the detection layer did, over a scored corpus. Spec: eval-002.

Everything before this says *what* the system decided. This says how well,
and the whole item turns out to be about what each figure is **indexed by**.

**Recall is indexed by truth, precision by prediction.** Recall's
denominator is the runs of a scenario type; precision's is the runs *given*
an anomaly type. A "per scenario type" row carrying both puts two
denominators under one name, and the two coincide only where no arm is ever
reported as another -- which is a result to report, not an assumption to
build on. So the arm rows and the type rows are separate objects, and the
only thing joining them is `f1`, which exists only where one arm maps to one
type. Today it exists for `possible_interference_zone` and not for
`possible_sensor_fault`, which two arms produce.

**The word recall means two different things in this project** and they
differ by more than twenty points: `anom-011` measures it per staged
aircraft on the track side (82 per cent on the navigation arm, 59 on each
suppression arm), this item measures it per run over reportable output.
Unlabelled in a write-up a reader can quote either for the other, so the
guard is mechanical: nothing here exports a bare `recall`, every key names
its denominator, and `anom-011`'s figure is carried beside this one in its
own object rather than merged into it.

**A wrong answer is two errors.** `anom-013` guarantees at most one claim
per zone, so a run reported as the wrong type is a false negative for the
type staged *and* a false positive for the type claimed. Three independent
binary problems would count that run once and lose half of it, which is why
this is one multi-class confusion over the reportable types.

**There are two false-positive rates and they are never pooled.** A report
on `normal-baseline` is invention from nothing. A report on
`aircraft-coverage-gap` is cross-modal leakage -- something real happening
on the track side reaching a radio verdict -- which is the specificity test
`research_scope.md` scoped that arm for. Both arms are silent arms, they
fail in different ways, and one figure over 120 runs cannot say which
failed. Only the first is backed by a control: `anom-008` grades quiet runs
only, so the cross-modal rate says on its face that it borrows no assurance
from the arm beside it.

**Latency is conditional on detection.** `anom-009` gives a value per claim
and this aggregates, so the aggregate exists only over the runs that
produced the right claim. Printed beside a recall below one it reads as a
property of the arm when it is a property of the successes, so it carries
the population it was taken over and says what that population is. A
detection carrying no latency is counted separately from one carrying a
latency of nothing, or the median moves quietly to whichever detections
happened to be instrumented.

**A rate over an empty population is `None`, never 0.0** -- `eval-005`'s
convention, which is also this item's named divide-by-zero failure case. The
item's original wording permitted "a documented undefined or zero
precision"; 0.0 is the value that destroys the distinction the failure case
was written to protect, so that half of the wording is superseded.

**The false-positive rate is refused without `anom-008`.** Zero is the
answer the control wants and also the answer a pipeline that never ran
gives, so a rate computed over ungraded quiet runs measures the pipeline and
not the rules. Every scored quiet run must carry a passing control, which
makes the item's own "which is why anom-008 must hold" mechanical rather
than a sentence in a document -- and both rates carry that control's
coverage figure, two reportable types of three, because read as three a
rate overstates the layer's coverage by exactly the rule that does not
exist.

**What makes an arm unjudged is the register, not this module.**
`aircraft-coverage-gap` stages something real, and the rule that would judge
it (`anom-006`) is registered as absent rather than clean. So the arm is
derived from `anom-008`'s register: build that rule and the arm becomes a
positive one with no edit here. The alternative -- writing "coverage-gap is
a negative arm" into a table -- would outlive the reason for it silently.

**Nothing here touches a database.** The outcomes arrive as the caller has
already read them, which keeps every join that reaches ground truth in the
open and lets the arithmetic be checked without Docker: `eval-004`'s sampler
and `eval-005`'s summariser take their inputs the same way.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from statistics import median
from typing import Any

from app.detection.control import QUIET, SOURCE_GAP_TYPE, Control, Kind, Producer
from app.detection.control import REGISTER as CONTROL_REGISTER
from app.evaluation.statistics import _rate

#: The confusion matrix's column for a run that reported nothing. Not an
#: anomaly type, and deliberately unspellable as one.
SILENT = "(silent)"


class MetricsError(ValueError):
    """A population, an outcome or a control these metrics refuse."""


class ArmKind(str, Enum):
    """What a scenario type is evidence *of*, which is not the same for all five.

    Three kinds and not two. `normal-baseline` and `aircraft-coverage-gap`
    are both silent arms and they are not the same test: the first asks
    whether the system invents an anomaly from nothing, the second whether a
    real disturbance on the track side leaks into a radio verdict. Pooling
    them loses the second, which is the one the baseline cannot make.
    """

    #: Stages something a built reportable rule is supposed to claim.
    POSITIVE = "positive"
    #: Stages nothing. Correct silence here is correct absolutely.
    SILENT_CONTROL = "silent-control"
    #: Stages something no *built* rule judges. Correct silence here is
    #: correct only because the rule that would judge it does not exist.
    UNJUDGED = "unjudged"


class NegativeArm(str, Enum):
    """The two false-positive rates, which are never pooled."""

    FROM_NOTHING = "from-nothing"
    CROSS_MODAL = "cross-modal"


#: What each of `scn-002`'s five types stages, in the vocabulary a reportable
#: rule uses -- ground truth, and the only place it is written down. A type
#: is *unjudged* rather than negative when the rule named here is registered
#: as absent, so `aircraft-coverage-gap` sits here with its true answer
#: rather than as a silence, and becomes a positive arm the day `anom-006`
#: is built. `normal-baseline` alone stages nothing.
STAGED_TYPE: Mapping[str, str | None] = {
    "aircraft-coverage-gap": SOURCE_GAP_TYPE,
    "ambiguous-mixed-evidence": "possible_sensor_fault",
    "gnss-degradation": "possible_interference_zone",
    "normal-baseline": None,
    "rf-sensor-fault": "possible_sensor_fault",
}

#: Which negative arm each silent scenario type supplies. Keyed on the
#: scenario type rather than on the kind, because the two arms differ by
#: *what was staged* and a kind cannot carry that.
_NEGATIVE_ARM: Mapping[str, NegativeArm] = {
    QUIET: NegativeArm.FROM_NOTHING,
    "aircraft-coverage-gap": NegativeArm.CROSS_MODAL,
}


def reportable_types(
    register: Mapping[tuple[str, str], Producer] = CONTROL_REGISTER,
) -> tuple[str, ...]:
    """Every type a reportable rule is registered to produce, built or not.

    Read off `anom-008`'s register rather than listed here, so the table and
    the coverage figure quoted beside it cannot disagree -- and so the type
    that has no implementation still gets a row, which is the record that it
    is missing rather than forgotten.
    """
    return tuple(
        sorted({p.finding_type for p in register.values() if p.kind is Kind.REPORTABLE})
    )


def _built_types(register: Mapping[tuple[str, str], Producer]) -> frozenset[str]:
    return frozenset(
        p.finding_type
        for p in register.values()
        if p.kind is Kind.REPORTABLE and p.built
    )


def arm_kind(
    scenario_type: str,
    *,
    register: Mapping[tuple[str, str], Producer] = CONTROL_REGISTER,
) -> ArmKind:
    """Which of the three kinds this arm is, given what is built today."""
    staged = STAGED_TYPE[scenario_type]
    if staged is None:
        return ArmKind.SILENT_CONTROL
    return ArmKind.POSITIVE if staged in _built_types(register) else ArmKind.UNJUDGED


@dataclass(frozen=True, slots=True)
class TrackSideRecall:
    """`anom-011`'s figure, carried beside this item's and never merged.

    A separate object rather than two fields on the arm row, because the two
    recalls have different denominators and the only reliable guard against
    quoting one for the other is that neither can be named without saying
    over what.
    """

    staged_aircraft: int
    detected_aircraft: int

    def __post_init__(self) -> None:
        if self.staged_aircraft < 0 or self.detected_aircraft < 0:
            raise MetricsError(
                f"a track-side recall of {self.detected_aircraft} of "
                f"{self.staged_aircraft} counts a negative number of aircraft."
            )
        if self.detected_aircraft > self.staged_aircraft:
            raise MetricsError(
                f"the track side detected more aircraft ({self.detected_aircraft}) "
                f"than were staged ({self.staged_aircraft}). anom-011 scores "
                "against the answer key, so a detection with nothing staged "
                "behind it is a join that went wrong rather than a rate above one."
            )

    @property
    def recall_per_staged_aircraft(self) -> float | None:
        return _rate(self.detected_aircraft, self.staged_aircraft)

    def as_json(self) -> dict[str, Any]:
        return {
            "staged_aircraft": self.staged_aircraft,
            "detected_aircraft": self.detected_aircraft,
            "recall_per_staged_aircraft": self.recall_per_staged_aircraft,
        }


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """One run: what was staged, and what reached an analyst.

    `reported` is the *reportable* anomaly types the run produced -- what
    `anom-013` let through, never an intermediate finding. A quiet run
    genuinely holds some 138 track discontinuities, and counted here they
    would make the false-positive rate one.
    """

    run_id: str
    scenario_type: str
    #: The reportable anomaly types this run claimed. Order carries nothing.
    reported: tuple[str, ...] = ()
    #: Whether the generator actually staged anything. A staged-type run that
    #: staged nothing is a baseline run wearing the wrong label and is
    #: excluded from every metric rather than only from recall: scored, a
    #: rule correctly reporting nothing on it counts as having missed
    #: something (`scn-006`, `anom-011`).
    staged: bool = True
    #: Signed seconds, from `anom-009`, on the claim that matched the truth.
    #: Never clamped: a negative value says the rule swept in readings from
    #: before the incident, and zero would read as instant detection.
    latency_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.scenario_type not in STAGED_TYPE:
            raise MetricsError(
                f"{self.scenario_type!r} is not one of the five scenario types. "
                "A sixth means the ground-truth table here is out of date, not "
                "that one run is odd, so it is refused rather than skipped."
            )
        if len(set(self.reported)) != len(self.reported):
            raise MetricsError(
                f"run {self.run_id} reports an anomaly type twice. A run is the "
                "unit here, so a repeated type is either two zones collapsed "
                "into one name or one zone counted twice, and the two are "
                "indistinguishable once it is in."
            )
        if self.scenario_type == QUIET and self.staged:
            raise MetricsError(
                f"run {self.run_id} is {QUIET!r} and claims to have staged "
                "something. That arm stages nothing by definition; a staged "
                "quiet run is a generator fault, not a scored outcome."
            )
        if self.latency_seconds is not None:
            truth = STAGED_TYPE[self.scenario_type]
            if truth is None or truth not in self.reported:
                raise MetricsError(
                    f"run {self.run_id} carries a latency but produced no claim "
                    "of the type it staged. Latency is conditional on "
                    "detection: a value here would be a delay before an answer "
                    "that was never given."
                )

    @property
    def detected(self) -> bool:
        """Whether this run claimed the type it staged."""
        truth = STAGED_TYPE[self.scenario_type]
        return truth is not None and truth in self.reported


@dataclass(frozen=True, slots=True)
class LatencyOverDetections:
    """How long an arm's successes took, and how many of them there were.

    `detections` is the population this is conditional on and `measured` is
    how many of those carried a figure. Two counts rather than one, because
    otherwise a median quietly describes whichever detections happened to be
    instrumented with nothing in the report saying how many that was.
    """

    detections: int
    measured: int
    median_seconds: float | None
    min_seconds: float | None
    max_seconds: float | None

    def as_json(self) -> dict[str, Any]:
        return {
            "conditional_on": "detections",
            "detections": self.detections,
            "measured": self.measured,
            "median_seconds": self.median_seconds,
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
        }


@dataclass(frozen=True, slots=True)
class ArmRecall:
    """One scenario type's row. Everything here is indexed by **truth**.

    No precision figure appears on this object and that is the point: its
    denominator is a different set of runs, and a row carrying both would put
    two populations under one label.
    """

    scenario_type: str
    kind: ArmKind
    #: The reportable type this arm stages, or `None` for the silent control.
    staged_type: str | None
    #: Scored runs. Excluded runs are not among them.
    runs: int
    #: Runs dropped for staging nothing, counted so a reader can see how many.
    excluded: int
    detected: int
    missed: int
    latency: LatencyOverDetections
    #: `anom-011`'s per-aircraft figure, when one was measured for this arm.
    track_side: TrackSideRecall | None = None

    @property
    def recall_per_run(self) -> float | None:
        """`None` on an arm with no true positives to have found.

        A silent control has none by construction and an unjudged arm has
        none because no built rule judges it, so a 0.0 here would read as a
        detector that looked and missed everything.
        """
        if self.kind is not ArmKind.POSITIVE:
            return None
        return _rate(self.detected, self.runs)

    @property
    def false_negative_rate(self) -> float | None:
        recall = self.recall_per_run
        return None if recall is None else 1.0 - recall

    def as_json(self) -> dict[str, Any]:
        return {
            "scenario_type": self.scenario_type,
            "kind": self.kind.value,
            "staged_type": self.staged_type,
            "runs": self.runs,
            "excluded": self.excluded,
            "detected": self.detected,
            "missed": self.missed,
            "recall_per_run": self.recall_per_run,
            "false_negative_rate": self.false_negative_rate,
            "latency": self.latency.as_json(),
            "track_side": (
                None if self.track_side is None else self.track_side.as_json()
            ),
        }


@dataclass(frozen=True, slots=True)
class TypePrecision:
    """One reportable type's row. Everything here is indexed by **prediction**.

    `arms` is what decides whether F1 exists: it is the harmonic mean of this
    type's precision and *an arm's* recall, so it has no referent at all
    where two arms produce one type. The reason is therefore readable off the
    data rather than carried as a sentence beside it.
    """

    anomaly_type: str
    #: Whether a rule producing this type exists. `anom-006` does not.
    built: bool
    #: The scenario types whose staged truth is this type, sorted.
    arms: tuple[str, ...]
    claimed_runs: int
    correct: int
    wrong: int
    #: The single arm's recall, when there is a single arm. Carried so `f1`
    #: is arithmetic over two stated numbers rather than a hidden lookup, and
    #: refused where there is not exactly one arm: the contradiction is made
    #: unconstructible rather than guarded twice, since two checks holding one
    #: rule can each be removed without the behaviour changing, and a rule
    #: nothing can break is a rule no test is proving.
    arm_recall_per_run: float | None = None

    def __post_init__(self) -> None:
        if self.arm_recall_per_run is not None and len(self.arms) != 1:
            raise MetricsError(
                f"{self.anomaly_type} carries a single arm's recall while "
                f"{len(self.arms)} arms produce it. There is no arm that "
                "figure is about, so an F1 computed from it would be a "
                "harmonic mean of two different populations."
            )

    @property
    def precision(self) -> float | None:
        return _rate(self.correct, self.claimed_runs)

    @property
    def f1_is_defined(self) -> bool:
        """Whether one arm and one type correspond, and both halves exist.

        The arm count is held at construction, so what is asked here is only
        whether the two rates were measured -- and `precision + recall > 0`
        because an arm that detected nothing of a type only ever claimed
        wrongly gives 0 and 0, whose harmonic mean is a division by zero
        rather than a score of zero.
        """
        precision, recall = self.precision, self.arm_recall_per_run
        return precision is not None and recall is not None and precision + recall > 0

    @property
    def f1(self) -> float | None:
        if not self.f1_is_defined:
            return None
        precision, recall = self.precision, self.arm_recall_per_run
        assert precision is not None and recall is not None  # f1_is_defined
        return 2 * precision * recall / (precision + recall)

    def as_json(self) -> dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "built": self.built,
            "arms": list(self.arms),
            "claimed_runs": self.claimed_runs,
            "correct": self.correct,
            "wrong": self.wrong,
            "precision": self.precision,
            "arm_recall_per_run": self.arm_recall_per_run,
            "f1": self.f1,
            "f1_is_defined": self.f1_is_defined,
        }


@dataclass(frozen=True, slots=True)
class FalsePositiveRate:
    """One silent arm's rate. There are two and they are never added together."""

    arm: NegativeArm
    scenario_type: str
    runs: int
    runs_with_a_report: int
    #: Whether `anom-008` graded every run behind this figure. True only for
    #: the quiet arm: that control grades `normal-baseline` and nothing else,
    #: so the cross-modal rate rests on the same pipeline having been
    #: exercised rather than on a verdict of its own.
    controlled: bool
    reportable_types_covered: int
    reportable_types_registered: int

    @property
    def rate(self) -> float | None:
        return _rate(self.runs_with_a_report, self.runs)

    @property
    def coverage(self) -> str:
        """`anom-008`'s coverage, quoted *with* the rate rather than beside it."""
        return f"{self.reportable_types_covered} of {self.reportable_types_registered}"

    def as_json(self) -> dict[str, Any]:
        return {
            "arm": self.arm.value,
            "scenario_type": self.scenario_type,
            "runs": self.runs,
            "runs_with_a_report": self.runs_with_a_report,
            "rate": self.rate,
            "controlled": self.controlled,
            "reportable_types": self.coverage,
        }


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    """The detection chapter's results table, with nothing pooled across it."""

    arms: tuple[ArmRecall, ...]
    types: tuple[TypePrecision, ...]
    false_positive_rates: tuple[FalsePositiveRate, ...]
    #: Truth to prediction to scored runs, with `SILENT` for a run that
    #: claimed nothing. A row can sum past its arm's run count when a run
    #: claimed two types, which `multi_claim_runs` counts rather than hides.
    confusion: Mapping[str, Mapping[str, int]]
    runs: int
    excluded: int
    multi_claim_runs: int = 0
    _arms: Mapping[str, ArmRecall] = field(default_factory=dict, repr=False)
    _types: Mapping[str, TypePrecision] = field(default_factory=dict, repr=False)

    def for_arm(self, scenario_type: str) -> ArmRecall:
        return self._arms[scenario_type]

    def for_type(self, anomaly_type: str) -> TypePrecision:
        return self._types[anomaly_type]

    def for_negative(self, arm: NegativeArm) -> FalsePositiveRate:
        for rate in self.false_positive_rates:
            if rate.arm is arm:
                return rate
        raise KeyError(arm)

    def as_json(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "excluded": self.excluded,
            "multi_claim_runs": self.multi_claim_runs,
            "arms": [arm.as_json() for arm in self.arms],
            "types": [kind.as_json() for kind in self.types],
            "false_positive_rates": [r.as_json() for r in self.false_positive_rates],
            "confusion": {
                truth: dict(sorted(row.items()))
                for truth, row in sorted(self.confusion.items())
            },
        }


def compute(
    outcomes: Iterable[RunOutcome],
    *,
    controls: Mapping[str, Control],
    track_side: Mapping[str, TrackSideRecall] | None = None,
    register: Mapping[tuple[str, str], Producer] = CONTROL_REGISTER,
) -> DetectionMetrics:
    """Score a corpus, refusing anything that would make a figure unreadable.

    `controls` is `anom-008`'s verdict per quiet run, keyed on the run id,
    and every scored quiet run must appear in it: zero reportable findings is
    the answer the control wants and also the answer a pipeline that never
    ran gives, so a false-positive rate over ungraded runs is a measurement
    of the pipeline. `track_side` is `anom-011`'s per-aircraft recall per
    arm, carried and never merged.
    """
    scored, excluded = _partitioned(list(outcomes), register)
    if not scored and not excluded:
        raise MetricsError(
            "there are no runs to score. A metrics report over an empty corpus "
            "is every rate None and says nothing, which reads as a measurement."
        )
    _check_controls(scored, controls)

    types = reportable_types(register)
    built = _built_types(register)
    arms = _arm_rows(scored, excluded, track_side, register)
    by_arm = {arm.scenario_type: arm for arm in arms}
    for scenario_type in track_side or {}:
        if scenario_type not in by_arm or by_arm[scenario_type].runs == 0:
            raise MetricsError(
                f"a track-side recall was supplied for {scenario_type!r}, "
                "which was not scored here. Two halves of one report would "
                "describe different populations with nothing saying so."
            )
        if STAGED_TYPE[scenario_type] is None:
            raise MetricsError(
                f"a track-side recall was supplied for {scenario_type!r}, which "
                "stages nothing. anom-011 scores staged aircraft against the "
                "answer key and refuses a run that staged none, so a figure "
                "here is a rate over an empty denominator wearing a number."
            )

    type_rows = tuple(
        _type_row(anomaly_type, scored, by_arm, built) for anomaly_type in types
    )
    return DetectionMetrics(
        arms=arms,
        types=type_rows,
        false_positive_rates=_negative_rows(scored, register),
        confusion=_confusion(scored),
        runs=len(scored),
        excluded=len(excluded),
        multi_claim_runs=sum(1 for run in scored if len(run.reported) > 1),
        _arms=by_arm,
        _types={row.anomaly_type: row for row in type_rows},
    )


def _partitioned(
    outcomes: list[RunOutcome], register: Mapping[tuple[str, str], Producer]
) -> tuple[list[RunOutcome], list[RunOutcome]]:
    """Scored runs and excluded ones, refusing a population it cannot read."""
    seen: set[str] = set()
    allowed = set(reportable_types(register))
    scored: list[RunOutcome] = []
    excluded: list[RunOutcome] = []
    for run in outcomes:
        if run.run_id in seen:
            raise MetricsError(
                f"run {run.run_id!r} appears twice. A run is the unit of every "
                "figure here, so a duplicate weights one run twice in a rate "
                "nothing else records."
            )
        seen.add(run.run_id)
        unknown = [t for t in run.reported if t not in allowed]
        if unknown:
            raise MetricsError(
                f"run {run.run_id} reports {unknown[0]!r}, which is not a "
                "reportable anomaly type in anom-008's register. An "
                "intermediate finding counted here would put a quiet run's "
                "~138 track discontinuities into the false-positive rate."
            )
        # `scn-006`'s exclusion: a staged type that staged nothing is a
        # baseline run wearing the wrong label, and it is dropped from every
        # figure rather than only from recall.
        target = excluded if (run.scenario_type != QUIET and not run.staged) else scored
        target.append(run)
    return scored, excluded


def _check_controls(scored: list[RunOutcome], controls: Mapping[str, Control]) -> None:
    quiet = {run.run_id for run in scored if run.scenario_type == QUIET}
    for run_id, control in controls.items():
        if run_id not in quiet:
            raise MetricsError(
                f"a control was supplied for run {run_id!r}, which is not in the "
                "population being scored. The control and the metrics would then "
                "describe different sets of runs with nothing saying which."
            )
        if control.run_id != run_id:
            raise MetricsError(
                f"the control filed under run {run_id!r} reports run "
                f"{control.run_id!r}. One of the two is wrong and neither is "
                "recoverable from the other."
            )
        if not control.holds:
            raise MetricsError(
                f"run {run_id} did not pass anom-008's control: "
                f"{[v.producer.key for v in control.verdicts if not v.holds]}. "
                "A false-positive rate over runs whose detectors may not have "
                "run measures the pipeline and not the rules."
            )
    ungraded = sorted(quiet - set(controls))
    if ungraded:
        raise MetricsError(
            f"{len(ungraded)} quiet run(s) carry no anom-008 control, starting "
            f"at {ungraded[0]!r}. Zero reportable findings is the answer the "
            "control wants and also the answer a detector that never ran gives, "
            "and no property of the count separates them."
        )


def _arm_rows(
    scored: list[RunOutcome],
    excluded: list[RunOutcome],
    track_side: Mapping[str, TrackSideRecall] | None,
    register: Mapping[tuple[str, str], Producer],
) -> tuple[ArmRecall, ...]:
    """One row per scenario type, run or not.

    A table that omits the arm nobody generated reads as a complete table of
    however many arms did run.
    """
    rows: list[ArmRecall] = []
    for scenario_type in sorted(STAGED_TYPE):
        runs = [r for r in scored if r.scenario_type == scenario_type]
        kind = arm_kind(scenario_type, register=register)
        detections = [r for r in runs if r.detected] if kind is ArmKind.POSITIVE else []
        measured = [
            r.latency_seconds for r in detections if r.latency_seconds is not None
        ]
        rows.append(
            ArmRecall(
                scenario_type=scenario_type,
                kind=kind,
                staged_type=STAGED_TYPE[scenario_type],
                runs=len(runs),
                excluded=sum(1 for r in excluded if r.scenario_type == scenario_type),
                detected=len(detections),
                missed=len(runs) - len(detections) if kind is ArmKind.POSITIVE else 0,
                latency=LatencyOverDetections(
                    detections=len(detections),
                    measured=len(measured),
                    median_seconds=median(measured) if measured else None,
                    min_seconds=min(measured) if measured else None,
                    max_seconds=max(measured) if measured else None,
                ),
                track_side=(track_side or {}).get(scenario_type),
            )
        )
    return tuple(rows)


def _type_row(
    anomaly_type: str,
    scored: list[RunOutcome],
    by_arm: Mapping[str, ArmRecall],
    built: frozenset[str],
) -> TypePrecision:
    claimed = [run for run in scored if anomaly_type in run.reported]
    correct = [run for run in claimed if STAGED_TYPE[run.scenario_type] == anomaly_type]
    arms = tuple(
        sorted(
            scenario_type
            for scenario_type, staged in STAGED_TYPE.items()
            if staged == anomaly_type and anomaly_type in built
        )
    )
    return TypePrecision(
        anomaly_type=anomaly_type,
        built=anomaly_type in built,
        arms=arms,
        claimed_runs=len(claimed),
        correct=len(correct),
        wrong=len(claimed) - len(correct),
        arm_recall_per_run=(by_arm[arms[0]].recall_per_run if len(arms) == 1 else None),
    )


def _negative_rows(
    scored: list[RunOutcome], register: Mapping[tuple[str, str], Producer]
) -> tuple[FalsePositiveRate, ...]:
    """A rate per silent arm. An arm whose rule got built leaves this table."""
    types = reportable_types(register)
    built = _built_types(register)
    rows: list[FalsePositiveRate] = []
    for scenario_type, arm in sorted(_NEGATIVE_ARM.items(), key=lambda kv: kv[1].value):
        if arm_kind(scenario_type, register=register) is ArmKind.POSITIVE:
            continue
        runs = [r for r in scored if r.scenario_type == scenario_type]
        rows.append(
            FalsePositiveRate(
                arm=arm,
                scenario_type=scenario_type,
                runs=len(runs),
                runs_with_a_report=sum(1 for r in runs if r.reported),
                controlled=scenario_type == QUIET,
                reportable_types_covered=len(built),
                reportable_types_registered=len(types),
            )
        )
    return tuple(rows)


def _confusion(scored: list[RunOutcome]) -> Mapping[str, Mapping[str, int]]:
    matrix: dict[str, dict[str, int]] = {t: {} for t in STAGED_TYPE}
    for run in scored:
        row = matrix[run.scenario_type]
        for predicted in run.reported or (SILENT,):
            row[predicted] = row.get(predicted, 0) + 1
    return matrix
