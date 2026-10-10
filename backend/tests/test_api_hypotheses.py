"""The hypothesis read endpoints. Spec: api-004, amended 2026-10-10.

The Hypotheses screen shows one explanation per conclusion: the reviewable
row, the first generation the hosted arm was asked for (`db-012`, eval-004's
SCORED_ORDINAL), so a verdict and a blind score refer to the same text. The
store holds five or six hosted rows and a template baseline per bundle, plus
trial rows written before the campaign; none of those is listed.

Two kinds of test.

**Contract parity.** The shapes are declared in
`frontend/src/types/hypotheses.ts` and as response models, compared in both
directions, and the closed vocabularies (confidence, review status, stored
grounding, a citation's verdict, generator) are compared against the
backend's own enums.

**The endpoints against a live database**, marked and skipped without one.
The detail re-runs `ai-008` on read, so a citation that fails is served with
its failure and never dropped, and a stored verdict that disagrees with the
re-run is served beside it rather than reconciled.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.grounding import CitationVerdict, check
from app.ai.hypothesis import Confidence
from app.ai.service import GenerationResult, GeneratorKind
from app.ai.template import generate
from app.db.bundles import stored_bundles_for_run
from app.db.hypotheses import GroundingStatus, ReviewStatus, record_grounding
from app.main import app
from tests.conftest import RUN_ID, requires_database
from tests.contracts import contract_paths, union_members
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read
from tests.test_ai_grounding import citing
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_db_hypotheses import (  # noqa: F401 -- a fixture
    OTHER_RUN_ID,
    a_call,
    neighbours,
)

HOSTED = GeneratorKind.HOSTED
TEMPLATE = GeneratorKind.TEMPLATE

CONTRACT_PATHS = contract_paths("hypotheses.ts")

SHAPES = (
    "HypothesisList",
    "HypothesisSummary",
    "HypothesisDetail",
    "HypothesisCitation",
    "HypothesisBundle",
    "AnalystVerdict",
)

#: The bundles as stored, so expectations come from the same objects.
ZONE = replace(zone_bundle(tracks=False), scenario_run_id=RUN_ID)
FAULT = replace(fault_bundle(), scenario_run_id=RUN_ID)


def _schemas() -> Any:
    """Imported late, so a missing module fails each test rather than the file."""
    from app.api.v1.schemas import hypotheses

    return hypotheses


def _save(
    factory: sessionmaker,
    bundle: int,
    *,
    hypothesis: Any,
    generator: GeneratorKind,
    requested: GeneratorKind,
    ordinal: int | None,
) -> int:
    from app.db.hypotheses import save_hypothesis

    result = GenerationResult(
        hypothesis=hypothesis,
        generator=generator,
        call=None if generator is TEMPLATE else a_call(),
    )
    return save_hypothesis(
        factory,
        bundle_id=bundle,
        result=result,
        requested_generator=requested,
        campaign_ordinal=ordinal,
    )


def _verdict(
    engine: Engine, row: int, verdict: str, note: str | None, hour: int
) -> None:
    with engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO analyst_feedback "
                "(hypothesis_id, verdict, note, created_at) "
                "VALUES (:h, :v, :n, :at)"
            ),
            {
                "h": row,
                "v": verdict,
                "n": note,
                "at": datetime(2026, 10, 10, hour, tzinfo=UTC),
            },
        )
        connection.commit()


def _get(engine: Engine, monkeypatch: pytest.MonkeyPatch, path: str) -> tuple[int, Any]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        response = client.get(f"/api/v1/hypotheses{path}")
    return response.status_code, response.json()


# --------------------------------------------------------------- contract parity


@pytest.mark.parametrize("name", SHAPES)
def test_each_hypothesis_shape_and_its_model_carry_the_same_fields(name: str) -> None:
    # spec: api-004 -- declared once per language, compared in both directions.
    declared = _interfaces(_read(CONTRACT_PATHS))
    model = getattr(_schemas(), name)

    assert name in declared
    assert set(declared[name]) == set(
        model.model_json_schema(by_alias=True)["properties"]
    )


@pytest.mark.parametrize(
    ("union", "values"),
    [
        ("HypothesisConfidence", {c.value for c in Confidence}),
        ("ReviewStatus", {s.value for s in ReviewStatus}),
        ("StoredGrounding", {g.value for g in GroundingStatus}),
        ("CitationGrounding", {v.value for v in CitationVerdict}),
        ("Generator", {g.value for g in GeneratorKind}),
    ],
)
def test_each_closed_vocabulary_is_the_backends_own(
    union: str, values: set[str]
) -> None:
    # spec: api-004 -- confidence is never a number, and no state is collapsed.
    assert set(union_members(_read(CONTRACT_PATHS), union)) == values


# ------------------------------------------------------------------ the endpoints


@pytest.fixture
def screen(
    migrated_database: Engine,
    factory: sessionmaker,
    neighbours: dict[str, int],  # noqa: F811
) -> dict[str, int]:
    """The store as the campaign left it, in miniature.

    `first` (a zone bundle): a trial row, hosted ordinals 1 and 2, and the
    template baseline. `second` (a fault bundle): its existing unnumbered
    template row, and a hosted ordinal 1 that fell back to the template.
    `other_run`: only an unnumbered template row, so no reviewable row.
    """
    # By kind, not by position: the reader orders a run's bundles by window
    # then subject, which puts the fault bundle ("RF-03") first.
    kind = {
        bundle.anomaly_type: bundle_id
        for bundle_id, bundle in stored_bundles_for_run(factory, RUN_ID)
    }
    first, second = kind[ZONE.anomaly_type], kind[FAULT.anomaly_type]
    zone_text = generate(ZONE)
    fault_text = generate(FAULT)
    rows = {
        "trial": _save(
            factory,
            first,
            hypothesis=zone_text,
            generator=HOSTED,
            requested=HOSTED,
            ordinal=None,
        ),
        "reviewed": _save(
            factory,
            first,
            hypothesis=zone_text,
            generator=HOSTED,
            requested=HOSTED,
            ordinal=1,
        ),
        "second_ask": _save(
            factory,
            first,
            hypothesis=zone_text,
            generator=HOSTED,
            requested=HOSTED,
            ordinal=2,
        ),
        "baseline": _save(
            factory,
            first,
            hypothesis=zone_text,
            generator=TEMPLATE,
            requested=TEMPLATE,
            ordinal=1,
        ),
        "fell_back": _save(
            factory,
            second,
            hypothesis=fault_text,
            generator=TEMPLATE,
            requested=HOSTED,
            ordinal=1,
        ),
    }
    return {**neighbours, "first": first, "second": second, **rows}


@pytest.mark.database
@requires_database
def test_the_list_holds_one_reviewable_explanation_per_conclusion(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- the hosted row at the scored ordinal, never the trial
    # row, a later ask or the template baseline; ordered by window then id.
    status, body = _get(migrated_database, monkeypatch, "")

    assert status == 200
    assert [h["id"] for h in body["hypotheses"]] == [
        screen["reviewed"],
        screen["fell_back"],
    ]


@pytest.mark.database
@requires_database
def test_a_conclusion_with_no_reviewable_row_is_counted_not_hidden(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- an absence is a number rather than silence.
    _, body = _get(migrated_database, monkeypatch, "")
    assert body["unreviewableBundles"] == 1


@pytest.mark.database
@requires_database
def test_a_summary_carries_its_bundles_facts_and_its_provenance(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- summary fields; a fallback names the template as its
    # generator, the hosted arm as asked, and fellBack true (ai-010).
    _, body = _get(migrated_database, monkeypatch, "")
    reviewed, fell_back = body["hypotheses"]

    assert reviewed["bundleId"] == screen["first"]
    assert reviewed["runId"] == RUN_ID
    assert reviewed["hypothesisTitle"] == generate(ZONE).hypothesis_title
    assert reviewed["confidence"] in {"Low", "Medium", "High"}
    assert reviewed["status"] == "New"
    assert (reviewed["anomalyType"], reviewed["ruleId"], reviewed["subject"]) == (
        ZONE.anomaly_type,
        ZONE.rule_id,
        ZONE.subject,
    )
    assert datetime.fromisoformat(reviewed["windowStart"]) == ZONE.time_window[0]
    assert datetime.fromisoformat(reviewed["windowEnd"]) == ZONE.time_window[1]
    assert (
        reviewed["generator"],
        reviewed["requestedGenerator"],
        reviewed["fellBack"],
    ) == (
        "hosted",
        "hosted",
        False,
    )
    assert (
        fell_back["generator"],
        fell_back["requestedGenerator"],
        fell_back["fellBack"],
    ) == (
        "template",
        "hosted",
        True,
    )


@pytest.mark.database
@requires_database
def test_a_summary_carries_the_latest_verdict_or_null(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- the latest verdict or null.
    _verdict(migrated_database, screen["reviewed"], "needs-more-evidence", None, 9)
    _verdict(migrated_database, screen["reviewed"], "confirm", "matches the zone", 11)

    _, body = _get(migrated_database, monkeypatch, "")
    reviewed, fell_back = body["hypotheses"]

    assert reviewed["latestVerdict"]["verdict"] == "confirm"
    assert reviewed["latestVerdict"]["note"] == "matches the zone"
    assert fell_back["latestVerdict"] is None


@pytest.mark.database
@requires_database
def test_the_detail_serves_every_field_of_the_explanation(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- every ai-001 field, provenance, status and the stored
    # grounding verdict, never collapsed.
    status, body = _get(migrated_database, monkeypatch, f"/{screen['reviewed']}")
    expected = generate(ZONE)

    assert status == 200
    assert body["id"] == screen["reviewed"]
    assert body["bundleId"] == screen["first"]
    assert body["reviewable"] is True
    assert body["hypothesisTitle"] == expected.hypothesis_title
    assert body["confidence"] == expected.confidence.value
    assert body["summary"] == expected.summary
    assert body["evidenceAgainstOrUncertainty"] == list(
        expected.evidence_against_or_uncertainty
    )
    assert body["alternativeExplanations"] == list(expected.alternative_explanations)
    assert body["recommendedHumanAction"] == expected.recommended_human_action
    assert [c["statement"] for c in body["supportingEvidence"]] == [
        c.statement for c in expected.supporting_evidence
    ]
    assert (body["generator"], body["requestedGenerator"], body["fellBack"]) == (
        "hosted",
        "hosted",
        False,
    )
    assert isinstance(body["modelId"], str)
    assert body["status"] == "New"
    assert body["grounding"] == "not_checked"


@pytest.mark.database
@requires_database
def test_a_template_row_names_no_model(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- modelId is null where no model answered.
    _, body = _get(migrated_database, monkeypatch, f"/{screen['fell_back']}")
    assert body["modelId"] is None
    assert body["fellBack"] is True


@pytest.mark.database
@requires_database
def test_any_stored_row_can_be_read_and_says_whether_it_is_reviewable(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- the detail serves any stored row, reviewable or not.
    for row in ("trial", "second_ask", "baseline"):
        status, body = _get(migrated_database, monkeypatch, f"/{screen[row]}")
        assert status == 200, row
        assert body["reviewable"] is False, row


@pytest.mark.database
@requires_database
def test_every_citation_carries_its_position_and_its_grounding_re_run_on_read(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- ai-008's check over the hypothesis and its own bundle,
    # one verdict per citation by position.
    _, body = _get(migrated_database, monkeypatch, f"/{screen['reviewed']}")
    expected = check(generate(ZONE), ZONE)

    assert [
        (c["position"], c["ruleId"], c["findingType"], c["grounding"])
        for c in body["supportingEvidence"]
    ] == [
        (f.position, f.rule_id, f.finding_type, f.verdict.value)
        for f in expected.findings
    ]


@pytest.mark.database
@requires_database
def test_a_citation_that_fails_is_served_with_its_failure_and_never_dropped(
    migrated_database: Engine,
    factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    screen: dict[str, int],
) -> None:
    # spec: api-004, hyp-002 -- and a stored verdict that disagrees with the
    # re-run is served beside it, not reconciled.
    [real, *_] = generate(ZONE).supporting_evidence
    hypothesis = citing(
        ZONE, (real.rule_id, real.finding_type), ("NOT-A-RULE", "not_a_finding")
    )
    row = _save(
        factory,
        screen["first"],
        hypothesis=hypothesis,
        generator=HOSTED,
        requested=HOSTED,
        ordinal=3,
    )
    record_grounding(factory, hypothesis_id=row, report=check(generate(ZONE), ZONE))

    _, body = _get(migrated_database, monkeypatch, f"/{row}")

    assert [c["grounding"] for c in body["supportingEvidence"]] == [
        "grounded",
        "unknown",
    ]
    assert body["grounding"] == "passed"


@pytest.mark.database
@requires_database
def test_the_detail_carries_its_bundles_context(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- run, anomaly type, rule, subject, window, area as
    # longitude and latitude, channels, and the receivers the evidence names.
    _, body = _get(migrated_database, monkeypatch, f"/{screen['reviewed']}")
    bundle = body["bundle"]

    assert bundle["runId"] == RUN_ID
    assert (bundle["anomalyType"], bundle["ruleId"], bundle["subject"]) == (
        ZONE.anomaly_type,
        ZONE.rule_id,
        ZONE.subject,
    )
    assert datetime.fromisoformat(bundle["windowStart"]) == ZONE.time_window[0]
    assert datetime.fromisoformat(bundle["windowEnd"]) == ZONE.time_window[1]
    assert (bundle["longitude"], bundle["latitude"]) == pytest.approx(
        (ZONE.affected_area.lon, ZONE.affected_area.lat)
    )
    assert bundle["channels"] == list(ZONE.affected_channels)
    assert bundle["receivers"] == ["RF-03", "RF-04"]


@pytest.mark.database
@requires_database
def test_the_receivers_include_every_receiver_the_evidence_names(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- a fault bundle names its receiver and the neighbours
    # it checked, each once, in order.
    _, body = _get(migrated_database, monkeypatch, f"/{screen['fell_back']}")
    assert body["bundle"]["receivers"] == ["RF-02", "RF-03", "RF-05"]


@pytest.mark.database
@requires_database
def test_the_verdict_history_is_served_oldest_first(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- verdict, note or null, createdAt, oldest first.
    _verdict(migrated_database, screen["reviewed"], "confirm", "second look", 11)
    _verdict(migrated_database, screen["reviewed"], "needs-more-evidence", None, 9)

    _, body = _get(migrated_database, monkeypatch, f"/{screen['reviewed']}")

    assert [(v["verdict"], v["note"]) for v in body["verdicts"]] == [
        ("needs-more-evidence", None),
        ("confirm", "second look"),
    ]
    assert datetime.fromisoformat(body["verdicts"][0]["createdAt"]) == datetime(
        2026, 10, 10, 9, tzinfo=UTC
    )


@pytest.mark.database
@requires_database
def test_a_row_with_no_verdict_serves_an_empty_history(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- empty, not null.
    _, body = _get(migrated_database, monkeypatch, f"/{screen['fell_back']}")
    assert body["verdicts"] == []


@pytest.mark.database
@requires_database
def test_an_unknown_id_is_a_404_naming_it(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- failure case: 404 with a JSON body, not 200 with null.
    status, body = _get(migrated_database, monkeypatch, "/987654")
    assert status == 404
    assert "987654" in body["detail"]


@pytest.mark.database
@requires_database
def test_a_non_integer_id_is_a_422(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- failure case.
    status, _ = _get(migrated_database, monkeypatch, "/not-a-number")
    assert status == 422


@pytest.mark.database
@requires_database
def test_another_runs_unreviewable_bundle_does_not_reach_the_list(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch, screen: dict[str, int]
) -> None:
    # spec: api-004 -- only reviewable rows are listed, whatever run they are in.
    _, body = _get(migrated_database, monkeypatch, "")
    assert screen["other_run"] not in {h["bundleId"] for h in body["hypotheses"]}
    assert OTHER_RUN_ID not in {h["runId"] for h in body["hypotheses"]}
