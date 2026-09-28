"""Asking twenty questions and keeping an honest account. Spec: ai-012.

Everything needed to ask **one** question exists, is tested and is measured
-- the adapter, the budget, the retry-then-fall-back, the grounding check,
the template, and `ai-011`'s composition of all five. This is the job that
asks twenty of them and comes out with a record a number can be published
from. It is a capability rather than a loop, because three of the things it
has to get right have no symptom when it gets them wrong.

**The rows `ai-003`'s port would have dropped.** The port's `generate`
returns the delivered hypothesis and nothing else. An *ungrounded* attempt
parsed, so it is a storable row that `db-002` appends with grounding FAILED
beside the one that replaced it -- and reached through the port that row
does not exist. Nothing complains: every bundle still gets an explanation
and the catch rate still reports a number, with no rows behind it. So this
asks through `ai-007`'s recorded path, which `ai-011` now types for it.

**The grounding count, once per arm.** `ai-007`'s injected checker already
feeds the ledger on every attempt it examines. A campaign re-checking the
delivered hypothesis *through that checker* would count each model
generation twice and halve the catch rate it reports as a result. So the
verdict written into a row comes from the pure `check`, which records
nothing, and the ledger is fed from exactly one place per arm: the fallback's
checker for the model arm, and this module's own checker for the baseline.

**The replacement is not counted against the arm that was asked.** A
template hypothesis is grounded by construction and always passes, so
counting a stand-in against the hosted arm would dilute the hosted catch
rate with template output -- in the direction that makes the model arm look
better the more often it failed. It is also not marked *checked*, because
`ai-007` does not check it: "not yet checked" is the true value and a
PASSED there claims a check that never ran.

**What is skipped and what stops the run.** A per-bundle generation failure
is recorded and skipped, following `scn-003` and `eval-001`: a campaign that
dies on bundle 14 of 20 has spent the money and kept nothing. `ai-009`'s
`BudgetExceeded` and `ai-003`'s `ConfigurationError` stop it -- they sit
outside the `GenerationError` tree precisely so that nothing converts them
into template output while every row reports itself as hosted, and this
module is the outermost enclosing handler, one layer above where `ai-009`
was worried about. Stopping still hands back the account of what was already
stored, for exactly the reason skipping exists.

**A run against a rate-limited provider must pace itself.** The first
scored campaign made 60 calls as fast as it could against a 30,000
tokens-per-minute ceiling with prompts averaging 4,909 tokens -- about six
calls a minute -- and the provider refused five of them. `ai-004` maps a 429
to `ProviderUnavailable`, which is a `GenerationError`, which this module
records and skips: the right handling for a provider that is **down** and the
wrong handling for one that is merely **busy**, since the refusal itself says
*try again in 5.09s*. Two of the five were generation 1, so two of twenty
bundles came out with no scored generation at all and the marking corpus
silently went from 20 bundles to 18 -- against a figure quoted on an ethics
approval form. That is the worst shape this failure could take: everything
succeeded, every figure was reported, and the shortfall appears only when the
pack is built.

So there is a pause between model calls, and it is deliberately **not a
retry**: retrying here would blur `ai-006`'s availability fallback into
`ai-007`'s correctness one, which this whole layer is built to keep apart,
and pacing prevents the condition rather than recovering from it. The pause
falls between *attempts*, not between successes -- a refused call is still a
call the provider counted, so pacing only the successes would accelerate into
exactly the condition that caused the refusal. The template baseline is never
paused: it makes no call, which is `ai-009`'s argument for keeping it out of
the budget.

**The sample is an input and is never invented here.** The corpus is fixed
before the campaign runs (`docs/scoring_rubric.md`), and a runner able to
choose its own bundles could choose them after seeing a result. Drawing it
is `eval-004`'s first pass, committed before the first scored generation.

**The record is an artefact, not a diagnostic**, and it serialises itself.
`ai-004` already paid for the alternative: the egress payload was measured
against a dict hand-written inside a measurement script while nothing in
`app/` serialised a bundle at all -- a right number about the wrong object,
which is harder to notice than a wrong number because every check you could
run on the measurement passes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from sqlalchemy.orm import Session, sessionmaker

from app.ai.assembly import AssembledArm
from app.ai.budget import BudgetExceeded, BudgetReport
from app.ai.fallback import Refusal, RefusalCategory
from app.ai.grounding import GroundingChecker, GroundingLedger, check
from app.ai.service import (
    ConfigurationError,
    GenerationError,
    GeneratorKind,
    HypothesisGenerator,
    Usage,
)
from app.db.hypotheses import GroundingStatus, record_grounding, save_hypothesis
from app.detection.bundle import EvidenceBundle

_LOG = logging.getLogger(__name__)

#: A `(bundle_id, bundle)` pair, which is the shape `evb-002`'s reader
#: returns. Taking that shape rather than a type of its own means the
#: sample can be handed straight from the store to here with nothing in
#: between to get wrong.
SampledBundle = tuple[int, EvidenceBundle]


class CampaignAborted(RuntimeError):
    """The run stopped, and here is what it had done by then.

    Not a `GenerationError`, following `BudgetExceeded` and
    `ConfigurationError` -- the two causes it wraps. Caught by either
    fallback, an abort finishes the campaign on template output while every
    row reports itself as a model's, which is the whole reason those two
    were carved out of that tree.

    It carries the partial record because the calls were paid for and the
    rows are in the database: an abort that dropped the account of which row
    was which would leave them unattributable, which is the same argument
    that makes a skipped bundle *recorded* rather than swallowed.
    """

    def __init__(
        self, message: str, *, record: CampaignRecord, cause: BaseException
    ) -> None:
        super().__init__(message)
        self.record = record
        #: Available as `__cause__` too; named here so a caller does not
        #: have to know which of the two stopped it by string matching.
        self.cause = cause


@dataclass(frozen=True, slots=True)
class RefusalRecord:
    """One attempt that was paid for and thrown away.

    `hypothesis_id` is `db-002`'s asymmetry made explicit. An ungrounded
    refusal parsed, so it has a row; a malformed one never became a
    hypothesis, so a reason and a counted call are its entire record and
    inventing a row for it would store a hypothesis nobody wrote.
    """

    attempt: int
    category: RefusalCategory
    reason: str
    hypothesis_id: int | None
    usage: Usage | None


@dataclass(frozen=True, slots=True)
class GenerationRecord:
    """One generation: what was asked, what answered, and where it went."""

    bundle_id: int
    #: Position within this bundle and this arm, counted from one.
    #: `eval-004` scores generation 1, so it has to be identifiable as
    #: generation 1 rather than found by row order -- and it lives here
    #: rather than in the schema because it is a fact about the experiment
    #: and not about the hypothesis. A deployed system generates once.
    ordinal: int
    requested_arm: GeneratorKind
    generator: GeneratorKind
    hypothesis_id: int
    grounding: GroundingStatus
    refusals: tuple[RefusalRecord, ...]
    usage: Usage | None
    seconds: float

    @property
    def fell_back(self) -> bool:
        """`db-002`'s definition, read from the record rather than the row."""
        return self.generator is not self.requested_arm


@dataclass(frozen=True, slots=True)
class SkippedGeneration:
    """One generation that failed and did not stop the run."""

    bundle_id: int
    ordinal: int
    requested_arm: GeneratorKind
    reason: str


@dataclass(frozen=True, slots=True)
class CampaignRecord:
    """Everything the campaign did, and the two ledgers it did it under."""

    generations: tuple[GenerationRecord, ...]
    skipped: tuple[SkippedGeneration, ...]
    budget: BudgetReport
    ledger: GroundingLedger

    def as_json(self) -> dict[str, Any]:
        """The artefact, in a shape `json.dumps` accepts unchanged.

        Per-arm and never pooled, following `eval-005`: a single pooled
        catch rate hides the difference being measured. Every arm appears,
        including one that never ran -- whose rate is `null` rather than
        0.0, because zero out of zero is unmeasured and a floor there reads
        as "the check flagged nothing on this arm".
        """
        return {
            "generations": [
                {
                    "bundle_id": generation.bundle_id,
                    "ordinal": generation.ordinal,
                    "requested_arm": generation.requested_arm.value,
                    "generator": generation.generator.value,
                    "fell_back": generation.fell_back,
                    "hypothesis_id": generation.hypothesis_id,
                    "grounding": generation.grounding.value,
                    "seconds": generation.seconds,
                    "usage": _usage_json(generation.usage),
                    "refusals": [
                        {
                            "attempt": refusal.attempt,
                            "category": refusal.category.value,
                            "reason": refusal.reason,
                            "hypothesis_id": refusal.hypothesis_id,
                            "usage": _usage_json(refusal.usage),
                        }
                        for refusal in generation.refusals
                    ],
                }
                for generation in self.generations
            ],
            "skipped": [
                {
                    "bundle_id": skipped.bundle_id,
                    "ordinal": skipped.ordinal,
                    "requested_arm": skipped.requested_arm.value,
                    "reason": skipped.reason,
                }
                for skipped in self.skipped
            ],
            "budget": {
                "calls": self.budget.call_count,
                "prompt_tokens": self.budget.prompt_tokens,
                "completion_tokens": self.budget.completion_tokens,
                "spent_usd": self.budget.spent_usd,
                "unpriced_calls": self.budget.unpriced_calls,
                # Whether `spent_usd` is the total or a lower bound. A
                # figure that quietly omitted the calls it could not price
                # would be worse than none, and `eval-005` reports cost as
                # a result.
                "cost_is_complete": self.budget.cost_is_complete,
            },
            "grounding": {
                arm.value: {
                    "checked": self.ledger.checked(arm),
                    "caught": self.ledger.caught(arm),
                    "catch_rate": self.ledger.catch_rate(arm),
                    "near_misses": [
                        finding.near_miss.value
                        for finding in self.ledger.near_misses(arm)
                        if finding.near_miss is not None
                    ],
                }
                for arm in GeneratorKind
            },
        }


def _usage_json(usage: Usage | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cost_usd": usage.cost_usd,
    }


def run_campaign(
    session_factory: sessionmaker[Session],
    *,
    sample: Sequence[SampledBundle],
    arm: AssembledArm,
    baseline: HypothesisGenerator,
    generations: int,
    pause_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> CampaignRecord:
    """Ask both arms about every bundle in the sample, and store every answer.

    `generations` applies to the **model arm only**. The baseline is asked
    once however many the model is asked, and that single generation is safe
    for exactly the reason the model arm's was not: there is no provider in
    it, so its repeatability is a property of the code rather than a claim
    about someone else's serving stack.

    `pause_seconds` has **no default**, on `ai-007`'s `max_attempts` rule: how
    fast a run may ask is a decision about the provider it is pointed at, and
    one made by omission is one nobody chose -- here the cost of not choosing
    is a corpus smaller than the pre-registered one, with nothing saying so.
    Derive it from the provider's published limit and the measured prompt
    size; `sleep` is injected so the suite can assert the pacing without
    waiting for it.

    The budget and the grounding ledger come off `arm`, because they span a
    **run** and not an arm -- `ai-011` hands them back for this.
    """
    _refuse_a_corpus_nobody_chose(sample, generations, pause_seconds)

    # The baseline's own checker. A separate instance from the one inside
    # the fallback, declaring a different arm and sharing the ledger: the
    # arm is declared and never read off a hypothesis, which carries no
    # record of what made it.
    baseline_check = GroundingChecker(arm=GeneratorKind.TEMPLATE, ledger=arm.ledger)

    made: list[GenerationRecord] = []
    skipped: list[SkippedGeneration] = []

    def so_far() -> CampaignRecord:
        return CampaignRecord(
            generations=tuple(made),
            skipped=tuple(skipped),
            budget=arm.budget.report(),
            ledger=arm.ledger,
        )

    asked = 0
    for bundle_id, bundle in sample:
        for ordinal in range(1, generations + 1):
            # Between attempts, not between successes: a refused call is
            # still a call the provider counted. And not before the first,
            # which buys nothing and delays every run by the interval.
            if asked:
                sleep(pause_seconds)
            asked += 1
            try:
                made.append(
                    _model_generation(
                        session_factory,
                        bundle_id=bundle_id,
                        bundle=bundle,
                        arm=arm,
                        ordinal=ordinal,
                    )
                )
            except (BudgetExceeded, ConfigurationError) as stopped:
                raise CampaignAborted(
                    f"the campaign stopped on bundle {bundle_id}, generation "
                    f"{ordinal} of the {arm.arm.value} arm: {stopped}",
                    record=so_far(),
                    cause=stopped,
                ) from stopped
            except GenerationError as failed:
                # Recorded and skipped. The remaining generations for this
                # bundle are still attempted: a provider that was
                # unreachable a moment ago may not be now, and the baseline
                # below is worth having either way.
                _LOG.warning(
                    "bundle %d generation %d of the %s arm failed and was "
                    "skipped: %s",
                    bundle_id,
                    ordinal,
                    arm.arm.value,
                    failed,
                )
                skipped.append(
                    SkippedGeneration(
                        bundle_id=bundle_id,
                        ordinal=ordinal,
                        requested_arm=arm.arm,
                        reason=str(failed) or type(failed).__name__,
                    )
                )

        try:
            made.append(
                _baseline_generation(
                    session_factory,
                    bundle_id=bundle_id,
                    bundle=bundle,
                    baseline=baseline,
                    grounding=baseline_check,
                )
            )
        except GenerationError as failed:
            _LOG.warning(
                "bundle %d produced no baseline and was skipped: %s",
                bundle_id,
                failed,
            )
            skipped.append(
                SkippedGeneration(
                    bundle_id=bundle_id,
                    ordinal=1,
                    requested_arm=GeneratorKind.TEMPLATE,
                    reason=str(failed) or type(failed).__name__,
                )
            )

    return so_far()


def _refuse_a_corpus_nobody_chose(
    sample: Sequence[SampledBundle], generations: int, pause_seconds: float
) -> None:
    """Four shapes that would report a campaign that did not happen."""
    if pause_seconds < 0:
        raise ConfigurationError(
            f"the campaign was configured to pause {pause_seconds} seconds "
            "between model calls. Time does not run backwards, and a negative "
            "interval is far more likely an arithmetic slip in a caller "
            "deriving one from a rate limit than a deliberate choice."
        )
    if not sample:
        raise ConfigurationError(
            "the campaign was given no bundles. It would succeed, cost "
            "nothing and report a catch rate of None on every arm -- which "
            "reads exactly like a clean run of an arm that was never asked "
            "anything."
        )
    seen: set[int] = set()
    for bundle_id, _ in sample:
        if bundle_id in seen:
            raise ConfigurationError(
                f"bundle {bundle_id} appears in the sample more than once. It "
                "would be counted twice in every per-arm figure while looking "
                "like two bundles, and the pre-registered corpus is 20 "
                "distinct bundles."
            )
        seen.add(bundle_id)
    if generations < 1:
        raise ConfigurationError(
            f"the campaign was configured for {generations} generation(s) per "
            "bundle from the model arm. It would ask the model nothing and "
            "report every bundle as baseline-only, which is a campaign that "
            "did not happen described as one that did."
        )


def _model_generation(
    session_factory: sessionmaker[Session],
    *,
    bundle_id: int,
    bundle: EvidenceBundle,
    arm: AssembledArm,
    ordinal: int,
) -> GenerationRecord:
    """One model generation, with every attempt it took to get there."""
    started = time.monotonic()
    outcome = arm.generator.generate_recorded(bundle)
    seconds = time.monotonic() - started

    refusals = tuple(
        _store_refusal(
            session_factory,
            bundle_id=bundle_id,
            bundle=bundle,
            arm=arm.arm,
            refusal=refusal,
        )
        for refusal in outcome.refusals
    )

    row = save_hypothesis(
        session_factory,
        bundle_id=bundle_id,
        result=outcome.result,
        requested_generator=arm.arm,
    )
    grounding = GroundingStatus.NOT_CHECKED
    if not outcome.fell_back:
        # The pure check, not the ledger-attached one: `ai-007`'s checker
        # has already recorded this hypothesis, and a second entry would
        # count the generation twice and halve the reported catch rate.
        report = check(outcome.result.hypothesis, bundle)
        record_grounding(session_factory, hypothesis_id=row, report=report)
        grounding = GroundingStatus.PASSED if report.passed else GroundingStatus.FAILED

    return GenerationRecord(
        bundle_id=bundle_id,
        ordinal=ordinal,
        requested_arm=arm.arm,
        generator=outcome.result.generator,
        hypothesis_id=row,
        grounding=grounding,
        refusals=refusals,
        usage=outcome.result.call.usage if outcome.result.call else None,
        seconds=seconds,
    )


def _store_refusal(
    session_factory: sessionmaker[Session],
    *,
    bundle_id: int,
    bundle: EvidenceBundle,
    arm: GeneratorKind,
    refusal: Refusal,
) -> RefusalRecord:
    """The attempt that was thrown away, kept as whatever survived of it."""
    row: int | None = None
    if refusal.result is not None:
        row = save_hypothesis(
            session_factory,
            bundle_id=bundle_id,
            result=refusal.result,
            requested_generator=arm,
        )
        # It failed the check by definition -- that is what ungrounded
        # means -- and the verdict is derived rather than asserted so the
        # row carries a report rather than a flag somebody set by hand.
        record_grounding(
            session_factory,
            hypothesis_id=row,
            report=check(refusal.result.hypothesis, bundle),
        )
    return RefusalRecord(
        attempt=refusal.attempt,
        category=refusal.category,
        reason=refusal.reason,
        hypothesis_id=row,
        usage=refusal.call.usage if refusal.call else None,
    )


def _baseline_generation(
    session_factory: sessionmaker[Session],
    *,
    bundle_id: int,
    bundle: EvidenceBundle,
    baseline: HypothesisGenerator,
    grounding: GroundingChecker,
) -> GenerationRecord:
    """`ai-002` over the same bundle, which is what makes the pair a pair.

    Checked through the ledger-attached checker rather than the pure one,
    because this is the only place the template's own catch rate is
    populated -- and that rate is the **oracle**: the template is grounded
    by construction, so anything flagged here is a defect in the check.

    `report` rather than the callable gate: a flagged baseline must be
    recorded and reported, not raised. Aborting would let a defect in the
    check destroy a campaign that has already been paid for, and `eval-005`
    reports the template's catch rate as a result either way.
    """
    started = time.monotonic()
    result = baseline.generate(bundle)
    seconds = time.monotonic() - started

    row = save_hypothesis(
        session_factory,
        bundle_id=bundle_id,
        result=result,
        requested_generator=GeneratorKind.TEMPLATE,
    )
    report = grounding.report(result.hypothesis, bundle)
    record_grounding(session_factory, hypothesis_id=row, report=report)

    return GenerationRecord(
        bundle_id=bundle_id,
        ordinal=1,
        requested_arm=GeneratorKind.TEMPLATE,
        generator=result.generator,
        hypothesis_id=row,
        grounding=GroundingStatus.PASSED if report.passed else GroundingStatus.FAILED,
        refusals=(),
        usage=result.call.usage if result.call else None,
        seconds=seconds,
    )


__all__ = [
    "CampaignAborted",
    "CampaignRecord",
    "GenerationRecord",
    "RefusalRecord",
    "SampledBundle",
    "SkippedGeneration",
    "run_campaign",
]
