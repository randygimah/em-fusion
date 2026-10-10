"""Storing a hypothesis, and what makes one reproducible. Spec: db-002.

The write path for everything Phase 9 produces. It takes `ai-003`'s
generation result -- the hypothesis plus what produced it -- and stores one
row, which is the shape the envelope was designed for.

**Two things this module refuses, in opposite directions.** A model arm's
row without its model id or its verbatim response, and a template row
carrying a model id. Both are `db-002`'s named failure cases and both are
deliberately a *second* guard: `ai-003` already makes such a result
unconstructible, so neither is reachable through the front door. They are
kept because a boundary check holds against a row assembled some other way,
and because this is the failure class nobody can repair afterwards -- a
campaign that ran against a model whose identity was not recorded is a
campaign that has to be run again.

**Writes append and never replace.** `db-008` replaces findings per run per
rule, and the asymmetry is principled rather than an oversight: a finding
is derived and regenerable from a seed, while a model call consumed money
and produced one specific response. Two calls are two facts. One bundle
legitimately carries a model hypothesis and the template that replaced it
after a grounding failure (`ai-007`), and a retry is a second call with its
own cost that `ai-009` has to count.

**Grounding is three-valued over a nullable column.** A hypothesis is
written before `ai-008` examines it, so `NULL` means *not yet checked* --
and the enum exists so that nothing can write `if not passed:` and treat
that identically to *failed*. `evb-001`'s principle, and the third time
this repository has had to state it. **And the verdict has a writer**
(`record_grounding`), added 2026-09-27: without one the column could hold
three states and only ever held the third, so a campaign stored every
verdict it had in its hand nowhere. It takes `ai-008`'s report rather than
a bool, which is what makes *not yet checked* unconstructible as an input
instead of merely refused -- `ai-011`'s preference, and the mapping from
report to stored value then exists once.

**A row says which arm was *asked* as well as which generator answered.**
The two differ exactly once and it is the case that matters: when the model
arm's answer fails `ai-008` and `ai-007` falls back, `ai-002` writes the
text, so `generator` says `template` -- truthfully -- and nothing records
that a model was asked first. The campaign also runs `ai-002` as the scored
baseline over the same bundle, so the two rows are then byte-identical, the
same deterministic generator over the same input, and one of them is the
hosted arm's delivery. `generator != requested_generator` is therefore the
**definition** of a fallback rather than a state to refuse: `ai-007` goes
model-to-template and `ai-006` goes hosted-to-local. Only one combination
is nonsense -- the template named as the arm that was asked while a model
answered -- and that is refused here, because nothing falls back *from* an
arm that makes no call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.ai.grounding import GroundingReport
from app.ai.hypothesis import Citation, Hypothesis
from app.ai.service import GenerationResult, GeneratorKind

if TYPE_CHECKING:
    from app.ai.campaign import GenerationRecord


class HypothesisWriteError(ValueError):
    """A row that would not be reproducible, refused before it is written."""


class ReviewStatus(str, Enum):
    """Where a hypothesis is in analyst review. FR-602.

    `New` is a genuine initial state rather than a placeholder for one, so
    a freshly written row is not claiming anything it has not earned. The
    rest belong to `fbk-001`.
    """

    NEW = "New"
    UNDER_REVIEW = "Under review"
    CONFIRMED = "Confirmed"
    REJECTED = "Rejected"
    INCONCLUSIVE = "Inconclusive"


class GroundingStatus(str, Enum):
    """Whether every claim was checked against the bundle, in three values.

    The stored column is a nullable boolean and this is the type that
    stops the third state collapsing into the second. `bool | None` invites
    `if not passed:`, which reads *not yet checked* as *failed* -- the
    exact substitution `evb-001` refuses for uncertainties, one layer up.
    """

    #: Written before `ai-008` ran. Not a verdict.
    NOT_CHECKED = "not_checked"
    PASSED = "passed"
    FAILED = "failed"

    @classmethod
    def from_stored(cls, value: bool | None) -> GroundingStatus:
        if value is None:
            return cls.NOT_CHECKED
        return cls.PASSED if value else cls.FAILED

    def to_stored(self) -> bool | None:
        if self is GroundingStatus.NOT_CHECKED:
            return None
        return self is GroundingStatus.PASSED


@dataclass(frozen=True, slots=True)
class StoredHypothesis:
    """One row, read back as the objects it was written from."""

    id: int
    bundle_id: int
    hypothesis: Hypothesis
    generator: GeneratorKind
    #: The arm that was **asked**, which is not always the one that
    #: answered. Read the pair through `fell_back`.
    requested_generator: GeneratorKind
    model_id: str | None
    generation_params: Mapping[str, Any] | None
    raw_response: str | None
    status: ReviewStatus
    grounding: GroundingStatus
    #: Its position in the campaign that wrote it (`db-012`), or None when it
    #: was not written by a campaign or the position is not known. Never
    #: inferred from row order.
    campaign_ordinal: int | None = None

    @property
    def fell_back(self) -> bool:
        """Whether something other than the arm that was asked answered.

        Derived in one place rather than at each consumer: `ai-010` renders
        it, `eval-005` counts it, and two spellings of the same comparison
        eventually disagree while both keep working.
        """
        return self.generator is not self.requested_generator


def check_reproducibility(
    *, generator: GeneratorKind, model_id: str | None, raw_response: str | None
) -> None:
    """Refuse a row whose provenance does not match the arm that made it.

    Both directions, so the `generator` column cannot lie either way. A
    model row missing its identity cannot be reproduced; a template row
    naming a model would make the campaign's per-arm counts wrong in the
    place nobody would think to check.
    """
    if generator is GeneratorKind.TEMPLATE:
        if model_id is not None or raw_response is not None:
            raise HypothesisWriteError(
                "a template hypothesis carries a model id or a raw response. "
                "No model ran, so those values are a fiction in the "
                "reproducibility columns, and every per-arm figure the "
                "campaign reports would count this row as a model's."
            )
        return
    # Stripped, matching `ai-003`'s ModelCall: an empty string satisfies a
    # check for "populated" while naming nothing, and a whitespace-only one
    # satisfies `if not model_id` too. Found by a test written to close a
    # mutation gap, which then found this.
    if not (model_id or "").strip():
        raise HypothesisWriteError(
            f"a {generator.value} hypothesis carries no model id. The model "
            "identity is the reproducibility claim (NFR-602), and a campaign "
            "that ran against a model nobody recorded has to be run again."
        )
    if not (raw_response or "").strip():
        raise HypothesisWriteError(
            f"a {generator.value} hypothesis carries no raw response. It is "
            "the verbatim pre-parse output, and its absence is discovered at "
            "the moment somebody investigates a grounding failure and finds a "
            "record of what was understood rather than of what was said."
        )


def check_requested_arm(
    *, generator: GeneratorKind, requested_generator: GeneratorKind
) -> None:
    """Refuse the one asked-for/answered pair that cannot have happened.

    Differing values are the **definition** of a fallback and are accepted
    in every direction a fallback really runs: `ai-007` ends at the template
    from either model arm, and `ai-006` ends at the local arm from the
    hosted one. What cannot happen is the template being the arm that was
    *asked* while a model answered: the template makes no call, needs no
    credential, and is the thing both fallbacks fall back **to**, so
    nothing ever falls back away from it.

    Refused here rather than in the database, following the split this
    table already uses: the column holds the vocabulary, the repository
    holds the meaning of a combination.
    """
    if (
        requested_generator is GeneratorKind.TEMPLATE
        and generator is not GeneratorKind.TEMPLATE
    ):
        raise HypothesisWriteError(
            f"a row says the template was the arm asked and the "
            f"{generator.value} arm answered. The template makes no call and "
            "is what both fallbacks fall back *to*, so nothing falls back "
            "away from it -- this row has the pair the wrong way round, and "
            "stored it would attribute a model's answer to the baseline in "
            "every per-arm figure the campaign reports."
        )


def save_hypothesis(
    session_factory: sessionmaker[Session],
    *,
    bundle_id: int,
    result: GenerationResult,
    requested_generator: GeneratorKind,
    campaign_ordinal: int | None = None,
) -> int:
    """Store one hypothesis against the bundle it explains, and say which row.

    Returns the new row's id because `ai-008` attaches a grounding verdict
    to one hypothesis and `fbk-001` attaches an analyst's, and a write that
    does not say what it made forces both of them to guess.

    `requested_generator` has **no default**, on `GenerationConfig.model_id`'s
    rule. The obvious default is `result.generator`, which is right on every
    row except the ones where an arm fell back -- and those are the only
    rows the column exists for, so a default would be wrong exactly where
    it was relied on.

    `campaign_ordinal` is the row's position in the campaign writing it
    (`db-012`), and absent means NULL: a row written outside a campaign is
    not a first generation.
    """
    call = result.call
    model_id = call.model_id if call else None
    raw_response = call.raw_response if call else None
    check_reproducibility(
        generator=result.generator, model_id=model_id, raw_response=raw_response
    )
    check_requested_arm(
        generator=result.generator, requested_generator=requested_generator
    )

    hypothesis = result.hypothesis
    with session_factory.begin() as session:
        return int(
            session.execute(
                text(
                    "INSERT INTO hypotheses ("
                    "  bundle_id, generator, requested_generator, model_id, "
                    "  generation_params, "
                    "  raw_response, hypothesis_title, confidence, summary, "
                    "  status, supporting_evidence, evidence_against_or_uncertainty, "
                    "  alternative_explanations, recommended_human_action, "
                    "  grounding_passed, campaign_ordinal"
                    ") VALUES ("
                    "  :bundle_id, :generator, :requested_generator, :model_id, "
                    "  CAST(:generation_params AS jsonb), :raw_response, "
                    "  :hypothesis_title, :confidence, :summary, :status, "
                    "  CAST(:supporting_evidence AS jsonb), "
                    "  CAST(:evidence_against AS jsonb), "
                    "  CAST(:alternatives AS jsonb), :recommended_human_action, "
                    "  :grounding_passed, :campaign_ordinal"
                    ") RETURNING id"
                ),
                {
                    "bundle_id": bundle_id,
                    "generator": result.generator.value,
                    "requested_generator": requested_generator.value,
                    "model_id": model_id,
                    # `None`, not `'null'`: an absent parameter set and a
                    # stored JSON null are different facts, and only the
                    # first is true of the template arm.
                    "generation_params": (
                        json.dumps(dict(call.parameters)) if call else None
                    ),
                    "raw_response": raw_response,
                    "hypothesis_title": hypothesis.hypothesis_title,
                    "confidence": hypothesis.confidence.value,
                    "summary": hypothesis.summary,
                    "status": ReviewStatus.NEW.value,
                    "supporting_evidence": json.dumps(
                        [
                            {
                                "rule_id": citation.rule_id,
                                "finding_type": citation.finding_type,
                                "statement": citation.statement,
                            }
                            for citation in hypothesis.supporting_evidence
                        ]
                    ),
                    "evidence_against": json.dumps(
                        list(hypothesis.evidence_against_or_uncertainty)
                    ),
                    "alternatives": json.dumps(
                        list(hypothesis.alternative_explanations)
                    ),
                    "recommended_human_action": hypothesis.recommended_human_action,
                    "grounding_passed": GroundingStatus.NOT_CHECKED.to_stored(),
                    "campaign_ordinal": campaign_ordinal,
                },
            ).scalar_one()
        )


_SELECT = (
    "SELECT id, bundle_id, generator, requested_generator, "
    "  model_id, generation_params, "
    "  raw_response, hypothesis_title, confidence, summary, status, "
    "  supporting_evidence, evidence_against_or_uncertainty, "
    "  alternative_explanations, recommended_human_action, "
    "  grounding_passed, campaign_ordinal "
    "FROM hypotheses "
)


def hypotheses_for_bundle(
    session_factory: sessionmaker[Session], bundle_id: int
) -> list[StoredHypothesis]:
    """Every hypothesis stored for one bundle, oldest first.

    Ordered by id rather than left to the heap. The order is the order the
    arms ran in, which is what makes a template row after a model row
    readable as the fallback it was -- and an unordered result is the
    failure this repository has recorded three times.
    """
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(_SELECT + "WHERE bundle_id = :bundle ORDER BY id"),
                {"bundle": bundle_id},
            )
            .mappings()
            .all()
        )
    return [_stored(row) for row in rows]


def _stored(row: Any) -> StoredHypothesis:
    return StoredHypothesis(
        id=row["id"],
        bundle_id=row["bundle_id"],
        hypothesis=Hypothesis(
            hypothesis_title=row["hypothesis_title"],
            confidence=row["confidence"],
            summary=row["summary"],
            supporting_evidence=tuple(
                Citation(**citation) for citation in row["supporting_evidence"]
            ),
            evidence_against_or_uncertainty=tuple(
                row["evidence_against_or_uncertainty"]
            ),
            alternative_explanations=tuple(row["alternative_explanations"]),
            recommended_human_action=row["recommended_human_action"],
        ),
        generator=GeneratorKind(row["generator"]),
        requested_generator=GeneratorKind(row["requested_generator"]),
        model_id=row["model_id"],
        generation_params=row["generation_params"],
        raw_response=row["raw_response"],
        status=ReviewStatus(row["status"]),
        grounding=GroundingStatus.from_stored(row["grounding_passed"]),
        campaign_ordinal=row["campaign_ordinal"],
    )


def record_grounding(
    session_factory: sessionmaker[Session],
    *,
    hypothesis_id: int,
    report: GroundingReport,
) -> None:
    """Attach `ai-008`'s verdict to one stored hypothesis.

    **The parameter is the report and not a status**, which is what makes
    *not yet checked* unconstructible here rather than merely refused: a
    report has two outcomes and neither of them is "nobody looked". The
    mapping from report to stored value then exists in exactly one place,
    so no caller can decide for itself that a failed check reads as
    unchecked -- the collapse `evb-001` refuses and this repository has now
    recorded four times.

    **An unknown row is refused rather than counted as written.** An
    `UPDATE` matching nothing is a success at the database and a silent loss
    at the caller, and the caller here is a campaign that has already paid
    for the answer whose verdict this is.

    Only `grounding_passed` is written. The review status belongs to the
    analyst (`fbk-001`), and a verdict that reset it would discard a human
    judgement on any row that was checked twice.
    """
    status = GroundingStatus.PASSED if report.passed else GroundingStatus.FAILED
    with session_factory.begin() as session:
        # `session.connection()` rather than `session.execute()`, which is
        # typed as returning a `Result` and does not carry `rowcount` -- the
        # one thing this needs from it. Same connection, same transaction,
        # following `db-007`'s completion writer, which refuses a missing run
        # for the same reason.
        result = session.connection().execute(
            text("UPDATE hypotheses SET grounding_passed = :passed WHERE id = :id"),
            {"passed": status.to_stored(), "id": hypothesis_id},
        )
        if result.rowcount != 1:
            raise HypothesisWriteError(
                f"no hypothesis with id {hypothesis_id} to record a grounding "
                f"verdict against: {result.rowcount} rows updated. The verdict "
                "belongs to a generation that was paid for, and an UPDATE "
                "matching nothing succeeds at the database while losing it here."
            )


@dataclass(frozen=True, slots=True)
class OrdinalCopy:
    """What copying the committed record's positions did, in counts."""

    written: int
    unchanged: int


def record_campaign_ordinals(
    session_factory: sessionmaker[Session],
    generations: Sequence[GenerationRecord],
) -> OrdinalCopy:
    """Copy each recorded generation's position onto its stored row. `db-012`.

    The record is the authority: an ordinal is copied, never computed. Any
    row the record disagrees with -- missing, under another bundle, asked of
    another arm, or already holding another position -- refuses the whole
    copy, in one transaction, so a half-copied store never exists. Running it
    twice changes nothing.
    """
    written = unchanged = 0
    with session_factory.begin() as session:
        for generation in generations:
            row = session.execute(
                text(
                    "SELECT bundle_id, requested_generator, campaign_ordinal "
                    "FROM hypotheses WHERE id = :id"
                ),
                {"id": generation.hypothesis_id},
            ).one_or_none()
            if row is None:
                raise HypothesisWriteError(
                    f"the record names hypothesis {generation.hypothesis_id}, "
                    "which is not in the store; nothing was written"
                )
            if row.bundle_id != generation.bundle_id:
                raise HypothesisWriteError(
                    f"hypothesis {generation.hypothesis_id} explains bundle "
                    f"{row.bundle_id} and the record says bundle "
                    f"{generation.bundle_id}; nothing was written"
                )
            if row.requested_generator != generation.requested_arm.value:
                raise HypothesisWriteError(
                    f"hypothesis {generation.hypothesis_id} was asked of the "
                    f"{row.requested_generator} arm and the record says "
                    f"{generation.requested_arm.value}; nothing was written"
                )
            if row.campaign_ordinal == generation.ordinal:
                unchanged += 1
                continue
            if row.campaign_ordinal is not None:
                raise HypothesisWriteError(
                    f"hypothesis {generation.hypothesis_id} already holds "
                    f"position {row.campaign_ordinal} and the record says "
                    f"{generation.ordinal}; it is not overwritten and nothing "
                    "was written"
                )
            session.execute(
                text("UPDATE hypotheses SET campaign_ordinal = :o WHERE id = :id"),
                {"o": generation.ordinal, "id": generation.hypothesis_id},
            )
            written += 1
    return OrdinalCopy(written=written, unchanged=unchanged)


@dataclass(frozen=True, slots=True)
class StoredVerdict:
    """One analyst verdict, as `analyst_feedback` holds it."""

    verdict: str
    note: str | None
    created_at: datetime


def hypotheses_at_position(
    session_factory: sessionmaker[Session],
    *,
    requested_generator: GeneratorKind,
    campaign_ordinal: int,
    bundle_ids: Sequence[int] | None = None,
) -> list[StoredHypothesis]:
    """Every row asked of one arm at one campaign position, by id. `api-004`.

    `bundle_ids` narrows it to those bundles (`api-019`, one run's); None
    means every bundle.
    """
    narrowed = "" if bundle_ids is None else "AND bundle_id = ANY(:bundles) "
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    _SELECT + "WHERE requested_generator = :arm "
                    "AND campaign_ordinal = :ordinal " + narrowed + "ORDER BY id"
                ),
                {
                    "arm": requested_generator.value,
                    "ordinal": campaign_ordinal,
                    "bundles": list(bundle_ids or ()),
                },
            )
            .mappings()
            .all()
        )
    return [_stored(row) for row in rows]


def hypothesis_by_id(
    session_factory: sessionmaker[Session], hypothesis_id: int
) -> StoredHypothesis | None:
    """One stored row, or None. `api-004`."""
    with session_factory.begin() as session:
        row = (
            session.execute(text(_SELECT + "WHERE id = :id"), {"id": hypothesis_id})
            .mappings()
            .one_or_none()
        )
    return None if row is None else _stored(row)


def bundles_with_hypotheses(session_factory: sessionmaker[Session]) -> set[int]:
    """Every bundle at least one stored hypothesis explains. `api-004`."""
    with session_factory.begin() as session:
        return {
            int(b)
            for (b,) in session.execute(
                text("SELECT DISTINCT bundle_id FROM hypotheses")
            ).all()
        }


def verdicts_for(
    session_factory: sessionmaker[Session], hypothesis_ids: Sequence[int]
) -> dict[int, list[StoredVerdict]]:
    """Each hypothesis's verdicts, oldest first; absent ids map to nothing."""
    if not hypothesis_ids:
        return {}
    with session_factory.begin() as session:
        rows = session.execute(
            text(
                "SELECT hypothesis_id, verdict, note, created_at "
                "FROM analyst_feedback WHERE hypothesis_id = ANY(:ids) "
                "ORDER BY created_at, id"
            ),
            {"ids": list(hypothesis_ids)},
        ).all()
    out: dict[int, list[StoredVerdict]] = {}
    for row in rows:
        out.setdefault(int(row.hypothesis_id), []).append(
            StoredVerdict(verdict=row.verdict, note=row.note, created_at=row.created_at)
        )
    return out


__all__ = [
    "GroundingStatus",
    "HypothesisWriteError",
    "OrdinalCopy",
    "StoredVerdict",
    "bundles_with_hypotheses",
    "hypotheses_at_position",
    "hypothesis_by_id",
    "record_campaign_ordinals",
    "verdicts_for",
    "ReviewStatus",
    "StoredHypothesis",
    "check_reproducibility",
    "check_requested_arm",
    "hypotheses_for_bundle",
    "record_grounding",
    "save_hypothesis",
]
