"""What a run is allowed to spend, and what it actually did. Spec: ai-009.

The project is about to start paying per request. This counts the requests,
records what each one cost, and **stops the run** when it has made too many
-- stops, rather than degrades.

**What it guards against is not the campaign.** Measured over the 41 real
bundles, a whole scored campaign is about 33,000 input tokens: single-digit
pounds at worst. The risk is a **loop** -- a retry that does not terminate,
a batch that regenerates on every poll, a test accidentally pointed at the
real provider. Two guards sit at different distances and only one of them
is here: the provider console's hard cap works when the code itself is the
broken thing, and this one notices in minutes rather than at the billing
boundary.

**The call ceiling is the guard; the spend ceiling is a tripwire.** The
item called them alternatives and they are not. A call count can be checked
*before* a call is made, so the ceiling **refuses** the call rather than
noticing it. Cost cannot be known until the answer comes back, so a spend
ceiling fires one call late by construction -- and `ai-003`'s
`Usage.cost_usd` is `float | None` on purpose, because a locally hosted
model genuinely costs nothing per call, so a spend ceiling on that arm
enforces nothing at all. A run configured with only the second has no
guard, which is why only the first is required.

**Exhaustion is not a generation failure.** `ai-006` catches unreachable
providers and `ai-007` catches unusable answers. A budget error shaped like
either would not stop the run: it would finish the campaign on template
output while the run reported itself as hosted -- the failure
`ConfigurationError` was carved out of the `GenerationError` tree to
prevent, arriving by a different road. `BudgetExceeded` is outside that
tree for the same reason.

**It wraps the arm, and the correctness fallback wraps it.** The ceiling
exists for a retry loop, so a budget placed *outside* `ai-007` would count
one call per bundle and miss every retry -- the only failure mode the item
names. Counting the calls that *failed* is the whole point, which is why
`ai-003`'s `GenerationRefused` carries the call it paid for.

**An unpriced call is unmeasurable, not free.** Total spend is a stated
lower bound whenever any call could not be priced, and the ledger says how
many. `eval-005` reports actual cost as a result, and a figure that quietly
omits what it could not price is worse than none.

One budget spans a whole run and therefore **both model arms**, since
`ai-006`'s hosted-to-local fallback is still one run and a budget held per
arm would let a run spend its ceiling twice. The template is not wrapped:
it makes no call and costs nothing, and counting fallbacks against a model
budget would abort a run for doing the safe thing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from app.ai.service import (
    ConfigurationError,
    GenerationError,
    GenerationRefused,
    GenerationResult,
    GeneratorKind,
    HypothesisGenerator,
    ModelCall,
    ProviderUnavailable,
)
from app.detection.bundle import EvidenceBundle

_LOG = logging.getLogger(__name__)

#: Recommended ceiling for one run. A number rather than a principle: five
#: times the largest plausible scored run (20 bundles, 2 arms, with retries)
#: and still trivially cheap at any current hosted price. The backstop is a
#: hard cap at the provider console -- about two orders of magnitude above
#: the expected campaign -- which lives outside this code deliberately,
#: because it is the guard that works when this code is the broken thing.
RECOMMENDED_MAX_CALLS = 200


class BudgetExceeded(RuntimeError):
    """The run has spent its allowance and must stop.

    **Deliberately not a `GenerationError`.** Caught by `ai-006` it would
    try the other arm and spend there; caught by `ai-007` it would produce
    a mechanical hypothesis for every remaining bundle while the run
    reported itself as hosted. Aborting is not degrading.

    It carries the ledger **as it stood**, because "the calls made so far
    are recorded" is only useful if the record reaches whoever handles the
    abort.
    """

    def __init__(self, message: str, *, report: BudgetReport) -> None:
        super().__init__(message)
        self.report = report


class CallOutcome(str, Enum):
    """How one call ended. All three cost an attempt; not all cost money."""

    #: An answer came back and the arm could use it.
    SERVED = "served"

    #: An answer came back and could not be used. Tokens were still spent,
    #: and these are what a retry loop is made of.
    REFUSED = "refused"

    #: Nothing was served. An attempt, and nothing to price.
    UNREACHABLE = "unreachable"


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One request, and what it cost.

    The arm is recorded here rather than read off a result, because a
    *refused* call has no result -- and that is precisely the call
    `eval-005`'s retry rate is made of.
    """

    ordinal: int
    arm: GeneratorKind
    outcome: CallOutcome
    call: ModelCall | None

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise GenerationError(
                f"a call recorded at ordinal {self.ordinal}. Calls are counted "
                "from one, because call zero is not a request that was made."
            )
        if self.arm is GeneratorKind.TEMPLATE:
            raise GenerationError(
                "a call attributed to the template arm. It makes no call and "
                "costs nothing, so this is a fiction in the column eval-005 "
                "reads as a per-arm result."
            )
        if self.outcome is CallOutcome.UNREACHABLE and self.call is not None:
            raise GenerationError(
                "an unreachable call carries a model call. Nothing was served, "
                "so there is nothing that could have been recorded -- and a "
                "priced record here would charge the run for a request the "
                "provider never answered."
            )
        if self.outcome is CallOutcome.SERVED and self.call is None:
            raise GenerationError(
                "a served call carries no model call. ai-003 makes a model "
                "arm's result unconstructible without one, so a record like "
                "this is a row that lost its provenance on the way here."
            )


@dataclass(frozen=True, slots=True)
class BudgetReport:
    """What a run had spent at one moment.

    A **snapshot**, not a view. The copy carried on a `BudgetExceeded` is
    evidence about the moment the run stopped; one that tracked the live
    ledger would be evidence about whenever it was eventually read.
    """

    calls: tuple[CallRecord, ...]
    max_calls: int
    max_cost_usd: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "calls", tuple(self.calls))

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def prompt_tokens(self) -> int:
        return sum(r.call.usage.prompt_tokens for r in self.calls if r.call)

    @property
    def completion_tokens(self) -> int:
        return sum(r.call.usage.completion_tokens for r in self.calls if r.call)

    @property
    def spent_usd(self) -> float:
        """What the run is known to have spent.

        A **lower bound** whenever `cost_is_complete` is false. An unpriced
        call contributes nothing here because nothing is known about it,
        which is a different statement from it having been free.
        """
        return sum(
            r.call.usage.cost_usd
            for r in self.calls
            if r.call is not None and r.call.usage.cost_usd is not None
        )

    @property
    def unpriced_calls(self) -> int:
        """Calls that consumed tokens and reported no price."""
        return sum(
            1
            for r in self.calls
            if r.call is not None and r.call.usage.cost_usd is None
        )

    @property
    def cost_is_complete(self) -> bool:
        """Whether `spent_usd` is the total or merely what could be priced."""
        return self.unpriced_calls == 0

    def calls_for(self, arm: GeneratorKind) -> tuple[CallRecord, ...]:
        """One arm's calls. `eval-005` reports per arm, never pooled."""
        return tuple(r for r in self.calls if r.arm is arm)


class CallBudget:
    """One run's allowance, and its ledger. Shared across both model arms."""

    def __init__(self, *, max_calls: int, max_cost_usd: float | None) -> None:
        if max_calls < 1:
            raise ConfigurationError(
                f"a run budgeted for {max_calls} calls cannot make one, and "
                "would report a run that never ran as a run that overspent."
            )
        if max_cost_usd is not None and max_cost_usd <= 0:
            raise ConfigurationError(
                f"a spend ceiling of {max_cost_usd} is not a ceiling -- it is a "
                "run that aborts on its first priced call while looking "
                "configured. Write None to mean there is no spend ceiling."
            )
        self.max_calls = max_calls
        self.max_cost_usd = max_cost_usd
        self._calls: list[CallRecord] = []

    def report(self) -> BudgetReport:
        """The ledger as it stands, detached from further changes."""
        return BudgetReport(
            calls=tuple(self._calls),
            max_calls=self.max_calls,
            max_cost_usd=self.max_cost_usd,
        )

    def approve(self) -> None:
        """Refuse the next call if there is no room for it.

        The **only** place the call ceiling is checked, and it runs before
        the request rather than after. That is the property separating a
        guard from an observation, and it is why this is not folded into
        one enforcement path with the spend ceiling below: a shared check
        after recording would abort on the call that *filled* the budget
        rather than the one that would exceed it, so a ceiling of N would
        let only N-1 calls return. Written that way first, and caught here.
        """
        report = self.report()
        if report.call_count >= self.max_calls:
            self._abort(
                f"the run has made {report.call_count} model call(s) against a "
                f"ceiling of {self.max_calls}, so this one is refused before "
                "it is made. A retry loop is the realistic route to an "
                "unexpected bill, so the run stops here rather than falling "
                "back to a mechanical explanation while reporting itself as a "
                "model arm.",
                report,
            )

    def record(
        self, arm: GeneratorKind, outcome: CallOutcome, call: ModelCall | None
    ) -> None:
        """Enter one call in the ledger, however it ended.

        The spend ceiling is checked here and nowhere else, because it
        *cannot* be checked anywhere else: cost is not known until the
        answer comes back. It therefore fires one call late by
        construction, and on an arm that reports no price it never fires at
        all. Both are why the call ceiling is the guard and this is a
        tripwire behind it.
        """
        self._calls.append(
            CallRecord(
                ordinal=len(self._calls) + 1, arm=arm, outcome=outcome, call=call
            )
        )
        report = self.report()
        if self.max_cost_usd is not None and report.spent_usd >= self.max_cost_usd:
            self._abort(
                f"the run has spent {report.spent_usd:.4f} USD against a cost "
                f"ceiling of {self.max_cost_usd}. The call that breached it was "
                "already paid for and its verbatim response is in the ledger, "
                "so what is lost by stopping here is the parsed hypothesis and "
                "not the thing that was bought.",
                report,
            )

    def _abort(self, message: str, report: BudgetReport) -> None:
        _LOG.error(
            "run budget exhausted after %d call(s), %.4f USD priced of %d "
            "unpriced: %s",
            report.call_count,
            report.spent_usd,
            report.unpriced_calls,
            message,
        )
        raise BudgetExceeded(message, report=report)


class BudgetedGenerator:
    """One model arm, counted. Wraps the arm; `ai-007` wraps this.

    A decorator over `ai-003`'s port, so the arm it wraps never learns it
    is being counted -- the same shape as the correctness fallback, and the
    reason both compose without either knowing about the other.
    """

    def __init__(
        self,
        inner: HypothesisGenerator,
        budget: CallBudget,
        *,
        arm: GeneratorKind,
    ) -> None:
        if arm is GeneratorKind.TEMPLATE:
            raise ConfigurationError(
                "the template arm was given a call budget. It makes no call "
                "and costs nothing, so counting it against a model budget "
                "would abort a run for doing the safe thing -- at exactly the "
                "moment a model arm was already in trouble."
            )
        self.inner = inner
        self.budget = budget
        self.arm = arm

    def generate(self, bundle: EvidenceBundle) -> GenerationResult:
        """Explain this bundle, if the run can still afford to ask."""
        self.budget.approve()
        try:
            result = self.inner.generate(bundle)
        except ProviderUnavailable:
            # An attempt, and nothing served to price. Counted, because a
            # loop against a dead provider is still a loop.
            self.budget.record(self.arm, CallOutcome.UNREACHABLE, None)
            raise
        except GenerationRefused as refused:
            # Tokens were spent on an answer nobody can use. These are what
            # a retry loop is made of, so they are the ones that must not
            # go uncounted.
            self.budget.record(self.arm, CallOutcome.REFUSED, refused.call)
            raise
        if result.generator is not self.arm:
            raise ConfigurationError(
                f"a generator declared as {self.arm.value} returned a "
                f"{result.generator.value} result. The declaration is what "
                "attributes a refused call, which has no result to read, so a "
                "disagreement here puts every per-arm figure in the wrong "
                "column silently."
            )
        self.budget.record(self.arm, CallOutcome.SERVED, result.call)
        return result


__all__ = [
    "RECOMMENDED_MAX_CALLS",
    "BudgetExceeded",
    "BudgetReport",
    "BudgetedGenerator",
    "CallBudget",
    "CallOutcome",
    "CallRecord",
]
