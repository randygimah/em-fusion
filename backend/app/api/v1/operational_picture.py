"""Operational picture route. Spec: api-002.

The one endpoint the dashboard reads. It holds no SQL, no session
construction and no spatial logic: `FR-904` puts all three in the repository,
and `db-006` is the test that says so once this route exists to assert against.
What is left here is the shape of the request -- which run, and how much of it.

**Which run is now a parameter, and the refusal is the item.** Spec: `api-013`.
With no parameter the behaviour is exactly `api-002`'s -- the newest completed
run, falling back to the newest -- so the contract, its parity test and the
frontend are untouched by the addition. With one, an unknown run is a **404 and
never a fall back to the newest**, which is the sharpest failure case here:
silently serving a different hour from the one asked for is indistinguishable
from the feature working, and it is exactly what the obvious implementation
does. The companion index lists the hours that may be asked for, and carries
neither a scenario type nor anything the detectors concluded -- the reasoning
is on `SelectableRun`.

**Separate calls, not one.** The run is chosen first and everything else read
for it afterwards, because "which run" is a policy question (`db-007`: prefer
one known to have finished) and the rest are queries. A single joined read
would work and would bury the policy inside SQL, where the reason for it cannot
be stated.

**Four reads for one payload, and the fourth is the item.** Spec: `api-012`.
Positions, findings, and whether a detection pass examined this run at all --
that last one cannot be inferred from the findings, because `db-008` replaces
them per run per rule *including at zero*, so a run examined and found clean
leaves exactly what a run nobody examined leaves. `anom-015` stamps the run,
and this reads the stamp.

**The layout is loaded, not queried.** `scn-005`'s receivers are configuration
the generator reads too, so they are served whether or not a pass has run; what
the pass governs is each receiver's *health*, which is `unknown` without one. On
every request rather than at import: `load_layout` fails loudly on a malformed
file, and a module-level read would turn that into an import error at startup
with no route to report it through.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.schemas.evidence import EvidenceAccount, build_evidence_account
from app.api.v1.schemas.operational_picture import (
    OperationalPicture,
    SelectableHour,
    ViewSelection,
    build_operational_picture,
)
from app.db.bundles import stored_bundles_for_run
from app.db.findings import findings_for_run, interference_radii_for_run
from app.db.repository import (
    detection_pass_for_run,
    latest_positions,
    latest_run,
    run_summary,
    selectable_hours,
)
from app.db.session import SessionFactory, get_sessionmaker
from app.scenario.layout import load_layout

router = APIRouter()

#: How far back from the end of a run its "current" picture reaches. Matches
#: the replay's own batch length, so a picture covers the last thing written
#: rather than a fraction of it or several batches of it.
FINAL_WINDOW_SECONDS = 300


@router.get("/operational-picture", tags=["operational-picture"])
def get_operational_picture(
    sessions: SessionFactory = Depends(get_sessionmaker),
    run_id: int | None = Query(default=None, alias="run"),
    view: ViewSelection = Query(default="all"),
) -> OperationalPicture:
    """The picture for one hour. spec: api-002, api-013.

    An empty database is a 200 with a null scenario rather than a 404 or a
    500: before the first run there is nothing to serve, and a screen that
    cannot render until someone has run a replay is a screen nobody can
    develop against (`op-001` requires it to render with scenario data absent).

    A **named** run that is not in the store is a 404, which is the opposite
    case and deliberately not the same one. Nothing was asked for in the first;
    something specific was asked for in the second, and answering it with a
    different hour is the failure `api-013` is built around. An absent store
    and an absent request are the honest empties; an absent *answer* to a
    present request is not.

    `view` (`api-007`) is the same distinction once more: absent is `all`, which
    every request received before the filter existed, and an unrecognised value
    is a 422 from the type rather than a quiet `all`.
    """
    run = latest_run(sessions) if run_id is None else run_summary(sessions, run_id)
    if run is None and run_id is not None:
        raise HTTPException(
            status_code=404,
            detail=f"no scenario run {run_id} in the store",
        )
    if run is None:
        return build_operational_picture(
            run=None, observations=[], layout=load_layout(), view=view
        )
    return build_operational_picture(
        run=run,
        observations=latest_positions(sessions, run.id, FINAL_WINDOW_SECONDS),
        layout=load_layout(),
        findings=findings_for_run(sessions, run.id),
        detection_pass=detection_pass_for_run(sessions, run.id),
        view=view,
        # The radius each interference claim was judged under, from the
        # settings stored with it -- never the detector's current one (`api-017`).
        zone_radii=interference_radii_for_run(sessions, run.id),
    )


@router.get("/operational-picture/hours", tags=["operational-picture"])
def get_selectable_hours(
    sessions: SessionFactory = Depends(get_sessionmaker),
) -> list[SelectableHour]:
    """The hours this endpoint will serve. spec: api-013.

    A **separate endpoint rather than a parameter on the picture**, because it
    answers a different question and is read at a different rate: the picture
    is polled every five seconds and this changes only when a batch completes.

    An empty store is an empty list and never a 404, on the same argument as
    the picture's own empty answer. The selection, and therefore the shape of
    this list, is `op-009`.
    """
    return [SelectableHour.of(row) for row in selectable_hours(sessions)]


@router.get("/operational-picture/evidence", tags=["operational-picture"])
def get_evidence(
    sessions: SessionFactory = Depends(get_sessionmaker),
    run_id: int | None = Query(default=None, alias="run"),
) -> EvidenceAccount | None:
    """Why this hour's conclusions were reached. spec: api-015.

    **Null means no detection pass examined this hour**, which is `api-012`'s
    distinction at a second endpoint: whether anybody looked is answered by the
    presence of the account and never by a number in it. An examined hour with
    nothing to report is three empty lists, and the two must not be one answer.
    An empty store is null on the same argument -- with no hour at all there is
    nothing that could have been examined, and `api-002`'s rule is that a screen
    which cannot render before the first run is a screen nobody can develop
    against.

    **No bundle is built here.** `anom-016` records that the pass does not fire
    per request and that the baseline, at 11.2 s, is the reason; and a bundle
    built under current settings served beside findings stored under the
    recorded ones would be two sources for one event. An hour whose claim has no
    stored bundle is reported as unexplained, which is the honest answer and the
    state of 140 of the 240 claim-bearing hours in the store.

    **Which hour is current is asked the same way the picture asks it** -- the
    same two calls in the same order -- because two endpoints answering that
    differently would show a panel belonging to another hour. An unknown run is
    a 404 and never the newest, `api-013`'s sharpest failure case repeated
    because it is the same mistake available at a second endpoint.

    **A separate endpoint rather than a field on the picture**: it is read on
    demand rather than every five seconds, it is an order of magnitude larger,
    and the picture's shape is a contract two parity tests hold in both
    directions.
    """
    run = latest_run(sessions) if run_id is None else run_summary(sessions, run_id)
    if run is None and run_id is not None:
        raise HTTPException(
            status_code=404,
            detail=f"no scenario run {run_id} in the store",
        )
    if run is None or detection_pass_for_run(sessions, run.id) is None:
        return None
    return build_evidence_account(
        run_id=run.id,
        findings=findings_for_run(sessions, run.id),
        bundles=stored_bundles_for_run(sessions, run.id),
    )
