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
this repository has had to state it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.ai.hypothesis import Citation, Hypothesis
from app.ai.service import GenerationResult, GeneratorKind


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
    model_id: str | None
    generation_params: Mapping[str, Any] | None
    raw_response: str | None
    status: ReviewStatus
    grounding: GroundingStatus


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


def save_hypothesis(
    session_factory: sessionmaker[Session],
    *,
    bundle_id: int,
    result: GenerationResult,
) -> int:
    """Store one hypothesis against the bundle it explains, and say which row.

    Returns the new row's id because `ai-008` attaches a grounding verdict
    to one hypothesis and `fbk-001` attaches an analyst's, and a write that
    does not say what it made forces both of them to guess.
    """
    call = result.call
    model_id = call.model_id if call else None
    raw_response = call.raw_response if call else None
    check_reproducibility(
        generator=result.generator, model_id=model_id, raw_response=raw_response
    )

    hypothesis = result.hypothesis
    with session_factory.begin() as session:
        return int(
            session.execute(
                text(
                    "INSERT INTO hypotheses ("
                    "  bundle_id, generator, model_id, generation_params, "
                    "  raw_response, hypothesis_title, confidence, summary, "
                    "  status, supporting_evidence, evidence_against_or_uncertainty, "
                    "  alternative_explanations, recommended_human_action, "
                    "  grounding_passed"
                    ") VALUES ("
                    "  :bundle_id, :generator, :model_id, "
                    "  CAST(:generation_params AS jsonb), :raw_response, "
                    "  :hypothesis_title, :confidence, :summary, :status, "
                    "  CAST(:supporting_evidence AS jsonb), "
                    "  CAST(:evidence_against AS jsonb), "
                    "  CAST(:alternatives AS jsonb), :recommended_human_action, "
                    "  :grounding_passed"
                    ") RETURNING id"
                ),
                {
                    "bundle_id": bundle_id,
                    "generator": result.generator.value,
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
                },
            ).scalar_one()
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
                text(
                    "SELECT id, bundle_id, generator, model_id, generation_params, "
                    "  raw_response, hypothesis_title, confidence, summary, status, "
                    "  supporting_evidence, evidence_against_or_uncertainty, "
                    "  alternative_explanations, recommended_human_action, "
                    "  grounding_passed "
                    "FROM hypotheses WHERE bundle_id = :bundle ORDER BY id"
                ),
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
        model_id=row["model_id"],
        generation_params=row["generation_params"],
        raw_response=row["raw_response"],
        status=ReviewStatus(row["status"]),
        grounding=GroundingStatus.from_stored(row["grounding_passed"]),
    )


__all__ = [
    "GroundingStatus",
    "HypothesisWriteError",
    "ReviewStatus",
    "StoredHypothesis",
    "check_reproducibility",
    "hypotheses_for_bundle",
    "save_hypothesis",
]
