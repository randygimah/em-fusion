"""The picture serves the explanations for the hour on screen. Spec: api-019.

The rail lists the hour's explanations as cards (`op-002`). The picture has
served an empty list since `api-002` because nothing produced them; `api-004`
now selects them, and this item hands the picture the same selection in the
same shape: `HypothesisSummary`, declared once and imported by the picture's
contract rather than redeclared.

Most examined hours hold conclusions with nothing to review (measured: 297
stored bundles over 280 hours, explanations for the bundles of 20), so an empty
list alone would read as "nothing concluded". `unexplainedConclusions` counts
them, and is null when nobody examined the hour.

Three kinds of test: contract parity, the pure builder, the endpoint.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.service import GeneratorKind
from app.ai.template import generate
from app.api.v1.schemas.hypotheses import HypothesisSummary, build_hypothesis_list
from app.api.v1.schemas.operational_picture import OperationalPicture
from app.db.bundles import stored_bundles_for_run
from app.db.hypotheses import (
    GroundingStatus,
    ReviewStatus,
    StoredHypothesis,
    save_hypothesis,
)
from app.db.repository import record_detection_pass
from app.main import app
from tests.conftest import RUN_ID, requires_database
from tests.contracts import contract_paths
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_api_hypotheses import _save
from tests.test_api_operational_picture import (
    LAYOUT,
    _detection_pass,
    _observation,
    _run,
)
from tests.test_db_hypotheses import (  # noqa: F401 -- a fixture
    OTHER_RUN_ID,
    neighbours,
)

HOSTED = GeneratorKind.HOSTED
TEMPLATE = GeneratorKind.TEMPLATE
PICTURE_CONTRACT = contract_paths("operationalPicture.ts")

ZONE = replace(zone_bundle(tracks=False), scenario_run_id=RUN_ID)
FAULT = replace(fault_bundle(), scenario_run_id=RUN_ID)
ELSEWHERE = replace(zone_bundle(tracks=False), scenario_run_id=RUN_ID + 1)


def _row(
    row_id: int,
    bundle_id: int,
    *,
    requested: GeneratorKind = HOSTED,
    generator: GeneratorKind | None = None,
    ordinal: int | None = 1,
    bundle: Any = ZONE,
) -> StoredHypothesis:
    answered = generator or requested
    return StoredHypothesis(
        id=row_id,
        bundle_id=bundle_id,
        hypothesis=generate(bundle),
        generator=answered,
        requested_generator=requested,
        model_id=None if answered is TEMPLATE else "a-model",
        generation_params=None,
        raw_response=None if answered is TEMPLATE else "{}",
        status=ReviewStatus.NEW,
        grounding=GroundingStatus.NOT_CHECKED,
        campaign_ordinal=ordinal,
    )


def _picture(**kwargs: Any) -> OperationalPicture:
    from app.api.v1.schemas.operational_picture import build_operational_picture

    kwargs.setdefault("run", _run())
    kwargs.setdefault("observations", [_observation()])
    kwargs.setdefault("detection_pass", _detection_pass())
    return build_operational_picture(layout=LAYOUT, **kwargs)


RUN_BUNDLES = {10: ZONE, 11: FAULT, 12: replace(FAULT, subject="RF-05")}


# --------------------------------------------------------------- contract parity


def test_the_pictures_hypotheses_are_the_list_endpoints_summaries() -> None:
    # spec: api-019 -- the very shape the list endpoint serves, declared once.
    field = OperationalPicture.model_fields["hypotheses"]
    assert field.annotation == list[HypothesisSummary]


def test_the_contract_imports_the_summary_rather_than_redeclaring_it() -> None:
    # spec: api-019 -- imported from hypotheses.ts; the old Hypothesis shape,
    # with its producer-less severity and free-text evidence, is gone.
    source = _read(PICTURE_CONTRACT)
    declared = _interfaces(source)

    assert declared["OperationalPicture"]["hypotheses"] == "HypothesisSummary[]"
    assert "HypothesisSummary" not in declared
    assert "Hypothesis" not in declared
    assert 'from "./hypotheses"' in source


def test_the_unexplained_count_is_a_nullable_number_on_both_sides() -> None:
    # spec: api-019 -- null when nobody examined the hour; never a 0 for that.
    declared = _interfaces(_read(PICTURE_CONTRACT))["OperationalPicture"]
    schema = OperationalPicture.model_json_schema(by_alias=True)["properties"]

    assert declared["unexplainedConclusions"] == "number | null"
    assert "unexplainedConclusions" in schema


# --------------------------------------------------------------------- assembly


def test_the_runs_reviewable_explanations_are_served_as_the_list_serves_them() -> None:
    # spec: api-019 -- api-004's selection, one definition: the same summaries,
    # in the same order, as the list endpoint builds from the same rows.
    rows = [_row(2, 11, bundle=FAULT), _row(1, 10)]
    picture = _picture(run_bundles=RUN_BUNDLES, hypothesis_rows=rows, verdicts={})

    expected = build_hypothesis_list(
        rows=rows, bundles=RUN_BUNDLES, verdicts={}, bundles_with_hypotheses={10, 11}
    ).hypotheses
    assert picture.hypotheses == expected
    assert [h.id for h in picture.hypotheses] == [1, 2]


def test_a_row_that_is_not_reviewable_never_appears() -> None:
    # spec: api-019 -- failure case: a trial row, a later ask, the template
    # baseline.
    rows = [
        _row(1, 10, ordinal=None),
        _row(2, 10, ordinal=2),
        _row(3, 10, requested=TEMPLATE),
    ]
    picture = _picture(run_bundles=RUN_BUNDLES, hypothesis_rows=rows, verdicts={})

    assert picture.hypotheses == []


def test_another_runs_explanation_never_appears() -> None:
    # spec: api-019 -- failure case: a row whose bundle is not this run's.
    rows = [_row(1, 10), _row(2, 99, bundle=ELSEWHERE)]
    picture = _picture(run_bundles=RUN_BUNDLES, hypothesis_rows=rows, verdicts={})

    assert [h.id for h in picture.hypotheses] == [1]


def test_conclusions_with_no_explanation_are_counted() -> None:
    # spec: api-019 -- failure case: an examined run with conclusions and no
    # explanation serves an empty list and their count.
    one = _picture(run_bundles=RUN_BUNDLES, hypothesis_rows=[_row(1, 10)], verdicts={})
    none = _picture(run_bundles=RUN_BUNDLES, hypothesis_rows=[], verdicts={})

    assert one.unexplainedConclusions == 2
    assert none.hypotheses == []
    assert none.unexplainedConclusions == 3


def test_an_examined_run_with_no_conclusions_counts_zero() -> None:
    # spec: api-019 -- failure case: an empty list and 0.
    picture = _picture(run_bundles={}, hypothesis_rows=[], verdicts={})

    assert picture.hypotheses == []
    assert picture.unexplainedConclusions == 0


def test_an_unexamined_run_counts_null_never_zero() -> None:
    # spec: api-019 -- failure case: whether anybody looked is not a number.
    picture = _picture(
        run_bundles=RUN_BUNDLES,
        hypothesis_rows=[_row(1, 10)],
        verdicts={},
        detection_pass=None,
    )

    assert picture.hypotheses == []
    assert picture.unexplainedConclusions is None


def test_the_view_does_not_filter_the_explanations() -> None:
    # spec: api-019 -- api-007 filters receivers, tracks and events only.
    rows = [_row(1, 10), _row(2, 11, bundle=FAULT)]
    served = {
        view: _picture(
            run_bundles=RUN_BUNDLES, hypothesis_rows=rows, verdicts={}, view=view
        )
        for view in ("all", "anomalous", "nominal")
    }

    assert served["all"].hypotheses == served["anomalous"].hypotheses
    assert served["all"].hypotheses == served["nominal"].hypotheses
    assert len(served["all"].hypotheses) == 2


def test_with_nothing_handed_over_the_picture_serves_no_explanations() -> None:
    # spec: api-019 -- the arguments default to nothing, so every existing
    # caller still builds a picture; examined with no bundles counts zero.
    picture = _picture()

    assert picture.hypotheses == []
    assert picture.unexplainedConclusions == 0


# ------------------------------------------------------------------ the endpoint


@pytest.mark.database
@requires_database
def test_the_endpoint_serves_the_pinned_runs_explanations_and_count(
    migrated_database: Engine,
    factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    neighbours: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-019 -- RUN_ID holds a zone and a fault bundle; only the zone
    # bundle has a reviewable row. The other run is unexamined.
    kind = {b.anomaly_type: i for i, b in stored_bundles_for_run(factory, RUN_ID)}
    zone = kind[ZONE.anomaly_type]
    reviewed = _save(
        factory,
        zone,
        hypothesis=generate(ZONE),
        generator=HOSTED,
        requested=HOSTED,
        ordinal=1,
    )
    save_hypothesis(
        factory,
        bundle_id=neighbours["other_run"],
        result=_template_result(),
        requested_generator=HOSTED,
        campaign_ordinal=1,
    )
    record_detection_pass(factory, RUN_ID, policy={"RF-NOISE.threshold_db": "6.0"})
    # The shared fixture seeds skeletal readings, enough for the bundle writer
    # to resolve citations against and not for the picture's position reader.
    # The bundles are stored by now and this test is about them, not readings.
    with migrated_database.connect() as connection:
        connection.execute(text("DELETE FROM observations"))
        connection.commit()

    monkeypatch.setenv(
        "DATABASE_URL", migrated_database.url.render_as_string(hide_password=False)
    )
    with TestClient(app) as client:
        here = client.get("/api/v1/operational-picture", params={"run": RUN_ID})
        there = client.get("/api/v1/operational-picture", params={"run": OTHER_RUN_ID})

    assert here.status_code == 200
    assert [h["id"] for h in here.json()["hypotheses"]] == [reviewed]
    assert here.json()["unexplainedConclusions"] == 1
    assert there.json()["hypotheses"] == []
    assert there.json()["unexplainedConclusions"] is None


def _template_result() -> Any:
    from app.ai.service import GenerationResult

    return GenerationResult(
        hypothesis=generate(ELSEWHERE), generator=TEMPLATE, call=None
    )
