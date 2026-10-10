"""The hypothesis read endpoints' shapes. Spec: api-004, amended 2026-10-10.

**One explanation per conclusion.** The store holds an experiment's output:
five or six rows asked of the hosted arm per bundle, the template baseline,
and trial rows written before the campaign. An analyst reviews one, the
*reviewable* row: asked of the hosted arm at eval-004's `SCORED_ORDINAL`
(`db-012`), so a verdict and a blind score refer to the same text. Where that
row itself fell back, its generator says template and `fellBack` is true, and
the screen shows the degradation (`ai-010`).

**Grounding is re-run on read**, `ai-008`'s pure check over the hypothesis and
its own bundle, one verdict per citation. A failing citation is served with its
failure and never dropped (`hyp-002`). The stored verdict is served beside it
and the two are not reconciled: they are different facts, one recorded at
generation and one computed now.

Pure builders over stored rows, as the picture's are; the route reads, these
assemble. Field names mirror `frontend/src/types/hypotheses.ts`, held by a
parity test in both directions.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.ai.grounding import CitationVerdict, check
from app.ai.hypothesis import Confidence
from app.ai.service import GeneratorKind
from app.db.hypotheses import (
    GroundingStatus,
    ReviewStatus,
    StoredHypothesis,
    StoredVerdict,
)
from app.detection.bundle import EvidenceBundle
from app.evaluation.pack import SCORED_ORDINAL

#: The arm an analyst reviews. The template is the baseline it is measured
#: against, never the explanation under review.
REVIEWED_ARM = GeneratorKind.HOSTED


class HypothesisError(RuntimeError):
    """The store holds something the reviewable selection cannot represent."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnalystVerdict(_Frozen):
    verdict: str
    note: str | None
    createdAt: datetime  # noqa: N815 -- mirrors the TypeScript contract


class HypothesisCitation(_Frozen):
    #: One-based, as `ai-008` prints it.
    position: int
    ruleId: str  # noqa: N815
    findingType: str  # noqa: N815
    statement: str
    #: Re-run on read; a failure is served, never dropped.
    grounding: CitationVerdict


class HypothesisBundle(_Frozen):
    runId: int  # noqa: N815
    anomalyType: str  # noqa: N815
    ruleId: str  # noqa: N815
    subject: str
    windowStart: datetime  # noqa: N815
    windowEnd: datetime  # noqa: N815
    longitude: float
    latitude: float
    channels: list[int]
    #: Every layout receiver the bundle's evidence names, each once, in order.
    receivers: list[str]


class HypothesisSummary(_Frozen):
    id: int
    bundleId: int  # noqa: N815
    runId: int  # noqa: N815
    hypothesisTitle: str  # noqa: N815
    confidence: Confidence
    status: ReviewStatus
    generator: GeneratorKind
    requestedGenerator: GeneratorKind  # noqa: N815
    fellBack: bool  # noqa: N815
    #: The stored model id verbatim, or null where no model answered (the
    #: template, a fallback included). Never a friendly name (qa.md 163).
    modelId: str | None  # noqa: N815
    anomalyType: str  # noqa: N815
    ruleId: str  # noqa: N815
    subject: str
    windowStart: datetime  # noqa: N815
    windowEnd: datetime  # noqa: N815
    latestVerdict: AnalystVerdict | None  # noqa: N815


class HypothesisList(_Frozen):
    hypotheses: list[HypothesisSummary]
    #: Bundles holding hypotheses but no reviewable row: an absence counted.
    unreviewableBundles: int  # noqa: N815


class HypothesisDetail(_Frozen):
    id: int
    bundleId: int  # noqa: N815
    reviewable: bool
    hypothesisTitle: str  # noqa: N815
    confidence: Confidence
    summary: str
    supportingEvidence: list[HypothesisCitation]  # noqa: N815
    evidenceAgainstOrUncertainty: list[str]  # noqa: N815
    alternativeExplanations: list[str]  # noqa: N815
    recommendedHumanAction: str  # noqa: N815
    generator: GeneratorKind
    requestedGenerator: GeneratorKind  # noqa: N815
    fellBack: bool  # noqa: N815
    modelId: str | None  # noqa: N815
    status: ReviewStatus
    #: As stored at generation; never collapsed to a boolean.
    grounding: GroundingStatus
    bundle: HypothesisBundle
    #: Oldest first; empty, never null.
    verdicts: list[AnalystVerdict]


def is_reviewable(row: StoredHypothesis) -> bool:
    return (
        row.requested_generator is REVIEWED_ARM
        and row.campaign_ordinal == SCORED_ORDINAL
    )


def build_hypothesis_list(
    *,
    rows: Sequence[StoredHypothesis],
    bundles: dict[int, EvidenceBundle],
    verdicts: dict[int, list[StoredVerdict]],
    bundles_with_hypotheses: Collection[int],
) -> HypothesisList:
    """Every reviewable row, by its bundle's window then id."""
    reviewable = [row for row in rows if is_reviewable(row)]
    seen: set[int] = set()
    for row in reviewable:
        if row.bundle_id in seen:
            raise HypothesisError(
                f"bundle {row.bundle_id} has two reviewable rows; db-012's "
                "index should have refused the second"
            )
        seen.add(row.bundle_id)
    reviewable.sort(key=lambda row: (bundles[row.bundle_id].time_window[0], row.id))
    return HypothesisList(
        hypotheses=[
            _summary(row, bundles[row.bundle_id], verdicts.get(row.id, []))
            for row in reviewable
        ],
        unreviewableBundles=len(set(bundles_with_hypotheses) - seen),
    )


def build_hypothesis_detail(
    *,
    row: StoredHypothesis,
    bundle: EvidenceBundle,
    verdicts: Sequence[StoredVerdict],
    receiver_ids: Collection[str],
) -> HypothesisDetail:
    """One stored row, its citations checked now, with its bundle's context."""
    hypothesis = row.hypothesis
    report = check(hypothesis, bundle)
    return HypothesisDetail(
        id=row.id,
        bundleId=row.bundle_id,
        reviewable=is_reviewable(row),
        hypothesisTitle=hypothesis.hypothesis_title,
        confidence=hypothesis.confidence,
        summary=hypothesis.summary,
        supportingEvidence=[
            HypothesisCitation(
                position=finding.position,
                ruleId=citation.rule_id,
                findingType=citation.finding_type,
                statement=citation.statement,
                grounding=finding.verdict,
            )
            for citation, finding in zip(
                hypothesis.supporting_evidence, report.findings, strict=True
            )
        ],
        evidenceAgainstOrUncertainty=list(hypothesis.evidence_against_or_uncertainty),
        alternativeExplanations=list(hypothesis.alternative_explanations),
        recommendedHumanAction=hypothesis.recommended_human_action,
        generator=row.generator,
        requestedGenerator=row.requested_generator,
        fellBack=row.fell_back,
        modelId=row.model_id,
        status=row.status,
        grounding=row.grounding,
        bundle=HypothesisBundle(
            runId=bundle.scenario_run_id,
            anomalyType=bundle.anomaly_type,
            ruleId=bundle.rule_id,
            subject=bundle.subject,
            windowStart=bundle.time_window[0],
            windowEnd=bundle.time_window[1],
            longitude=bundle.affected_area.lon,
            latitude=bundle.affected_area.lat,
            channels=list(bundle.affected_channels),
            receivers=_receivers(bundle, receiver_ids),
        ),
        verdicts=[_verdict(v) for v in verdicts],
    )


def _summary(
    row: StoredHypothesis, bundle: EvidenceBundle, verdicts: Sequence[StoredVerdict]
) -> HypothesisSummary:
    return HypothesisSummary(
        id=row.id,
        bundleId=row.bundle_id,
        runId=bundle.scenario_run_id,
        hypothesisTitle=row.hypothesis.hypothesis_title,
        confidence=row.hypothesis.confidence,
        status=row.status,
        generator=row.generator,
        requestedGenerator=row.requested_generator,
        fellBack=row.fell_back,
        modelId=row.model_id,
        anomalyType=bundle.anomaly_type,
        ruleId=bundle.rule_id,
        subject=bundle.subject,
        windowStart=bundle.time_window[0],
        windowEnd=bundle.time_window[1],
        latestVerdict=_verdict(verdicts[-1]) if verdicts else None,
    )


def _verdict(verdict: StoredVerdict) -> AnalystVerdict:
    return AnalystVerdict(
        verdict=verdict.verdict, note=verdict.note, createdAt=verdict.created_at
    )


def _receivers(bundle: EvidenceBundle, receiver_ids: Collection[str]) -> list[str]:
    """Layout receivers named in any evidence item's source, sorted."""
    sources = " ".join(item.source for item in bundle.evidence)
    return sorted(
        rid for rid in receiver_ids if re.search(rf"\b{re.escape(rid)}\b", sources)
    )


__all__ = [
    "REVIEWED_ARM",
    "AnalystVerdict",
    "HypothesisBundle",
    "HypothesisCitation",
    "HypothesisDetail",
    "HypothesisError",
    "HypothesisList",
    "HypothesisSummary",
    "build_hypothesis_detail",
    "build_hypothesis_list",
    "is_reviewable",
]
