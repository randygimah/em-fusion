"""The hypothesis read endpoints. Spec: api-004, amended 2026-10-10.

`GET /hypotheses` lists one explanation per conclusion, the reviewable row
(`db-012`); `GET /hypotheses/{id}` serves any stored row, saying whether it is
the reviewable one. Reading only: the verdict is `api-005`'s.

**Threat to validity, recorded with the item.** Both payloads name each
explanation's generator, so nothing built on them is shown to the second
rater before their blind scoring is done.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.schemas.hypotheses import (
    REVIEWED_ARM,
    HypothesisDetail,
    HypothesisList,
    build_hypothesis_detail,
    build_hypothesis_list,
)
from app.db.bundles import stored_bundles_by_id
from app.db.hypotheses import (
    bundles_with_hypotheses,
    hypotheses_at_position,
    hypothesis_by_id,
    verdicts_for,
)
from app.db.session import SessionFactory, get_sessionmaker
from app.evaluation.pack import SCORED_ORDINAL
from app.scenario.layout import load_layout

router = APIRouter()


@router.get("/hypotheses", tags=["hypotheses"])
def get_hypotheses(
    sessions: SessionFactory = Depends(get_sessionmaker),
) -> HypothesisList:
    """Every reviewable explanation, one per conclusion. spec: api-004."""
    rows = hypotheses_at_position(
        sessions, requested_generator=REVIEWED_ARM, campaign_ordinal=SCORED_ORDINAL
    )
    return build_hypothesis_list(
        rows=rows,
        bundles=stored_bundles_by_id(sessions, sorted({r.bundle_id for r in rows})),
        verdicts=verdicts_for(sessions, [r.id for r in rows]),
        bundles_with_hypotheses=bundles_with_hypotheses(sessions),
    )


@router.get("/hypotheses/{hypothesis_id}", tags=["hypotheses"])
def get_hypothesis(
    hypothesis_id: int,
    sessions: SessionFactory = Depends(get_sessionmaker),
) -> HypothesisDetail:
    """One stored explanation, its citations checked on read. spec: api-004."""
    row = hypothesis_by_id(sessions, hypothesis_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"no hypothesis {hypothesis_id} in the store"
        )
    bundle = stored_bundles_by_id(sessions, [row.bundle_id])[row.bundle_id]
    return build_hypothesis_detail(
        row=row,
        bundle=bundle,
        verdicts=verdicts_for(sessions, [row.id]).get(row.id, []),
        receiver_ids=[s.sensor_id for s in load_layout().sensors],
    )
