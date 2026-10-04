"""The screen can ask why. Spec: `api-015`.

The endpoint that turns a conclusion into the evidence behind it. Almost all
of it is a pure function over two things the store already holds -- this
hour's reported claims, and this hour's stored bundles -- so most of this
suite needs no database.

**The item is the accounting, not the evidence.** A bundle already exists,
already has every absence typed and every citation resolved. What did not
exist is a shape in which *the absence of a bundle* is a statement. Measured
on the store of record there are 160 quiet hours, 100 hours whose claim has
its bundle, and **140 hours whose claim has none** -- the newest hours all
being in the third group, because the pass builds bundles and throws them
away. Served as a bare list of bundles, those three states are one empty
list, which is the dash `op-003` had to replace with a sentence.

**Two-sided completeness**, after the amendment. `explained` plus
`unexplained` account for every reported claim; `explained` plus `unclaimed`
account for every stored bundle. There is no key joining the two tables --
there cannot be, since findings are replaced per run per rule and a foreign
key would cascade-delete the bundles on every re-score -- so they are matched
on `(run, rule id, type, window)`, which measurement showed unique on both
sides. The subject is deliberately not in that key: a fusion bundle's subject
is the receivers that deviated together, joined, and its claim's is the one
representative, so a key including it misses every interference bundle in the
store while matching every fault.

**The grouping re-organises and computes nothing.** One test walks the whole
serialised payload and requires every value in it to appear verbatim on an
item, an uncertainty, or the bundle's own metadata -- with a count of the
items a group lists as the only arithmetic allowed. That is `eval-007`'s
replacement constraint, which exists because the first version of this rule
("never summarise") was backwards.

**These tests run against bundles the real builder produced**, through
`evb-001`'s own fixtures, for the reason `evb-002`'s first draft recorded:
asserting against the test file's idea of a bundle tests the author's model
of a bundle and passes before anything exists.
"""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.schemas.evidence import (
    NO_CURRENT_CLAIM,
    NOT_BUNDLED,
    EvidenceAccount,
    EvidenceError,
    build_evidence_account,
)
from app.dal.models import DataMode, Location
from app.detection.bundle import EvidenceBundle, Grounding, UncertaintyKind
from app.detection.control import REGISTER, Kind, Producer, build_register
from app.detection.findings import DetectionFinding
from app.main import app
from app.scenario.incident import ScenarioType
from tests.conftest import requires_database
from tests.test_ai_template import fault_bundle, zone_bundle

BACKEND_ROOT = Path(__file__).resolve().parents[1]

EVIDENCE_PATH = "/api/v1/operational-picture/evidence"

RUN_ID = 4210
#: The two test bundles are built over this window by `evb-001`'s fixtures.
START = datetime(2022, 6, 27, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------- helpers


def claim_for(bundle: EvidenceBundle, *, run_id: int = RUN_ID) -> DetectionFinding:
    """The `db-008` row the pass stores for this bundle's conclusion.

    Built from the bundle on the four fields that are the match key, and
    **deliberately not on the subject**: a fusion claim's stored subject is
    one representative receiver where the bundle's is the joined list, so a
    helper that copied it across would make every test agree with a key the
    store disagrees with.
    """
    return DetectionFinding(
        scenario_run_id=run_id,
        rule_id=bundle.rule_id,
        finding_type=bundle.anomaly_type,
        subject=bundle.subject.split(", ")[0],
        started_at=bundle.time_window[0],
        ended_at=bundle.time_window[1],
        location=bundle.affected_area,
    )


def intermediate(
    *, rule_id: str = "RF-NOISE", finding_type: str = "rf_noise_deviation"
) -> DetectionFinding:
    """A finding no rule reports. A quiet hour holds about 138 of these."""
    return DetectionFinding(
        scenario_run_id=RUN_ID,
        rule_id=rule_id,
        finding_type=finding_type,
        subject="RF-03:4",
        started_at=START,
        ended_at=START + timedelta(seconds=30),
        location=Location(lat=51.5, lon=6.0),
    )


def account(
    *,
    findings: list[DetectionFinding] | None = None,
    bundles: list[tuple[int, EvidenceBundle]] | None = None,
    register: Any = REGISTER,
) -> EvidenceAccount:
    return build_evidence_account(
        run_id=RUN_ID,
        findings=findings or [],
        bundles=bundles or [],
        register=register,
    )


def zone(run_id: int = RUN_ID, **kw: Any) -> EvidenceBundle:
    return replace(zone_bundle(**kw), scenario_run_id=run_id)


def fault(run_id: int = RUN_ID, **kw: Any) -> EvidenceBundle:
    return replace(fault_bundle(**kw), scenario_run_id=run_id)


def group_for(claim: Any, pair: tuple[str, str]) -> Any:
    found = [g for g in claim.evidence if (g.ruleId, g.findingType) == pair]
    assert len(found) == 1, f"{pair} appears {len(found)} times"
    return found[0]


# ------------------------------------------------------------- the accounting


def test_a_claim_with_a_bundle_is_explained() -> None:
    # spec: api-015
    bundle = fault()

    got = account(findings=[claim_for(bundle)], bundles=[(7, bundle)])

    assert [c.bundleId for c in got.explained] == [7]
    assert got.unexplained == []
    assert got.unclaimed == []


def test_a_claim_with_no_bundle_is_unexplained_and_says_why() -> None:
    """The state of 140 of the 240 claim-bearing hours in the store, and of
    every hour the selector offers first."""
    # spec: api-015, api-012
    bundle = fault()

    got = account(findings=[claim_for(bundle)])

    assert got.explained == []
    assert [(c.ruleId, c.findingType, c.reason) for c in got.unexplained] == [
        (bundle.rule_id, bundle.anomaly_type, NOT_BUNDLED)
    ]


def test_the_two_lists_partition_every_reported_claim() -> None:
    """The guarantee, and what makes a dropped conclusion unconstructible
    rather than refused: it cannot vanish by omission, because its omission
    breaks this count."""
    # spec: api-015
    explained_bundle, other = fault(), zone()

    got = account(
        findings=[claim_for(explained_bundle), claim_for(other)],
        bundles=[(7, explained_bundle)],
    )

    assert len(got.explained) + len(got.unexplained) == 2
    assert [c.bundleId for c in got.explained] == [7]
    assert [c.findingType for c in got.unexplained] == [other.anomaly_type]


def test_an_intermediate_finding_is_in_neither_list() -> None:
    """A quiet run holds about 138 track discontinuities. Listed as claims
    they would present the layer's working material as conclusions."""
    # spec: api-015, anom-008, anom-010
    got = account(findings=[intermediate(), intermediate(finding_type="x")])

    assert (got.explained, got.unexplained, got.unclaimed) == ([], [], [])


def test_reportable_is_derived_from_the_register_and_not_spelled_here() -> None:
    """The register is injected, so this keeps asserting the rule rather than
    the current state of the ladder: a rule that becomes reportable reaches
    this endpoint with no edit, which is `api-012`'s own arrangement."""
    # spec: api-015, api-012, anom-008
    register = build_register(
        Producer(
            rule_id="RF-NOISE", finding_type="rf_noise_deviation", kind=Kind.REPORTABLE
        )
    )

    got = account(findings=[intermediate()], register=register)

    assert [c.findingType for c in got.unexplained] == ["rf_noise_deviation"]


def test_a_quiet_hour_is_three_empty_lists() -> None:
    """Not a refusal and not a null -- the hour was examined and there was
    nothing to report, which is `anom-008`'s required outcome on 60 of 60
    quiet runs."""
    # spec: api-015, anom-008
    got = account()

    assert (got.runId, got.explained, got.unexplained, got.unclaimed) == (
        RUN_ID,
        [],
        [],
        [],
    )


def test_a_bundle_matching_no_claim_is_carried_as_unclaimed() -> None:
    """Live on the corpus rather than hypothetical: four of 103 stored
    bundles are off by one or two sampling intervals at one end of the
    window, written before `anom-007`'s window derivation settled. Dropped
    silently, an hour reads as fully explained while some of its evidence
    was discarded."""
    # spec: api-015, evb-003
    bundle = fault()
    moved = replace(
        bundle,
        time_window=(bundle.time_window[0], bundle.time_window[1] + timedelta(seconds=10)),
    )

    got = account(findings=[claim_for(bundle)], bundles=[(7, moved)])

    assert [(b.bundleId, b.reason) for b in got.unclaimed] == [(7, NO_CURRENT_CLAIM)]
    assert [c.reason for c in got.unexplained] == [NOT_BUNDLED]


def test_the_match_key_does_not_include_the_subject() -> None:
    """A fusion bundle's subject is the receivers that deviated together,
    joined; its claim's is the one representative. A key including it misses
    all 41 interference bundles in the store while matching every fault,
    which is the shape of a defect that looks like a feature on half a
    corpus."""
    # spec: api-015
    bundle = zone()
    assert ", " in bundle.subject  # the premise, so the test cannot rot quietly

    got = account(findings=[claim_for(bundle)], bundles=[(7, bundle)])

    assert [c.bundleId for c in got.explained] == [7]


def test_an_explained_claim_names_the_receivers_the_bundle_names() -> None:
    """The bundle's subject and not the claim's, because this is what the
    panel has to name -- and the claim's representative already reaches the
    screen through the timeline."""
    # spec: api-015, api-012
    bundle = zone()

    got = account(findings=[claim_for(bundle)], bundles=[(7, bundle)])

    assert got.explained[0].subject == bundle.subject


def test_the_lists_follow_the_order_the_claims_arrive_in() -> None:
    """The findings reader orders by `started_at, subject, id`; an unordered
    payload takes its order from the heap, which this repository has had to
    fix three times."""
    # spec: api-015, api-012
    first, second = fault(), replace(fault(), subject="RF-07")
    later = replace(
        second,
        time_window=(
            second.time_window[0] + timedelta(seconds=60),
            second.time_window[1] + timedelta(seconds=60),
        ),
    )

    got = account(findings=[claim_for(later), claim_for(first)])

    assert [c.observedFrom for c in got.unexplained] == [
        later.time_window[0].isoformat(),
        first.time_window[0].isoformat(),
    ]


# ---------------------------------------------------------------- the grouping


def test_items_of_one_rule_and_type_become_one_group() -> None:
    # spec: api-015, eval-007
    bundle = zone()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    pairs = [(g.ruleId, g.findingType) for g in claim.evidence]
    assert len(pairs) == len(set(pairs))
    assert len(pairs) < len(bundle.evidence)


def test_the_grouping_key_is_the_pair_and_never_the_rule_alone() -> None:
    """`anom-012` borrows `anom-010`'s rule id, so a rate excess and a
    discontinuity are identical by rule id in every interference bundle this
    corpus produces -- the fourth place that collision has had to be
    handled. Keyed on the rule alone, the two collapse and the aircraft
    side's measured ratio is filed under its raw material."""
    # spec: api-015, ai-001, anom-010, anom-012
    bundle = zone()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    track = [g.findingType for g in claim.evidence if g.ruleId == "TRACK-GAP"]
    assert sorted(track) == ["track_continuity_gap", "track_rate_excess"]


def test_a_group_counts_the_items_it_lists() -> None:
    """The only arithmetic this endpoint is allowed."""
    # spec: api-015, eval-007
    bundle = fault()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    group = group_for(claim, ("SENSOR-FAULT", "neighbour_nominal"))
    assert group.count == 2


def test_identical_wording_collapses_to_one_statement_carrying_its_sources() -> None:
    """`eval-007`'s factoring, which it learned on fourteen rows repeating one
    sentence. Two receivers deviated by the same amount, and that is one
    sentence about two receivers rather than two sentences."""
    # spec: api-015, eval-007, op-010
    bundle = zone()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    group = group_for(claim, ("RF-NOISE", "rf_noise_deviation"))
    assert len(group.statements) == 1
    assert group.statements[0].count == 2
    assert group.statements[0].sources == ["RF-03:4", "RF-04:4"]


def test_distinct_wordings_stay_distinct() -> None:
    """The factoring is a collapse of identical strings and never a summary:
    two neighbours measured nominal say two different things, and one
    sentence standing for both would be a sentence the rule never wrote."""
    # spec: api-015, eval-007
    bundle = fault()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    group = group_for(claim, ("SENSOR-FAULT", "neighbour_nominal"))
    assert len(group.statements) == 2
    assert [s.count for s in group.statements] == [1, 1]


def test_a_group_spans_the_earliest_start_and_the_latest_end_of_its_items() -> None:
    """A selection of two values that are present, not an aggregate of
    them."""
    # spec: api-015, eval-007
    bundle = zone()
    items = [i for i in bundle.evidence if i.finding_type == "track_continuity_gap"]
    assert len({i.started_at for i in items}) == 2  # the premise

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    group = group_for(claim, ("TRACK-GAP", "track_continuity_gap"))
    assert group.observedFrom == min(i.started_at for i in items).isoformat()
    assert group.observedTo == max(i.ended_at for i in items).isoformat()


def test_a_group_lists_its_distinct_sources_in_the_order_they_appear() -> None:
    # spec: api-015
    bundle = zone()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    group = group_for(claim, ("TRACK-GAP", "track_continuity_gap"))
    assert group.sources == ["AC-48089ab4e5a9", "AC-aaaa1111"]


def test_the_payload_computes_no_value_that_is_not_already_in_the_bundle() -> None:
    """`eval-007`'s replacement constraint, mechanically. Its first form was
    "grouping must never summarise", on the grounds that a summarising pack
    would flatter the weaker arm -- which is backwards, since the template's
    citations *are* summaries. The form that survives is this: every rendered
    value appears verbatim in the source, and a count of the items a group
    lists is the only arithmetic.
    """
    # spec: api-015, eval-007
    bundle = zone()
    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    allowed: set[Any] = {7, RUN_ID, bundle.subject, bundle.rule_id, bundle.anomaly_type}
    for item in bundle.evidence:
        allowed |= {
            item.source,
            item.finding,
            item.rule_id,
            item.finding_type,
            item.grounding.value,
            item.data_mode.value,
            item.started_at.isoformat(),
            item.ended_at.isoformat(),
        }
    for unknown in bundle.known_uncertainties:
        allowed |= {unknown.kind.value, unknown.statement, unknown.subject}
    allowed |= {bundle.affected_area.lat, bundle.affected_area.lon}
    allowed |= set(bundle.affected_channels)
    allowed |= {t.isoformat() for t in bundle.time_window}
    # Counts, and nothing else numeric that is not already above.
    counts = {g.count for g in claim.evidence} | {
        s.count for g in claim.evidence for s in g.statements
    }

    for value in _scalars(claim.model_dump()):
        assert value in allowed or value in counts, f"{value!r} is in no source"


def _scalars(value: Any) -> list[Any]:
    """Every leaf of a nested payload."""
    if isinstance(value, dict):
        return [leaf for inner in value.values() for leaf in _scalars(inner)]
    if isinstance(value, list):
        return [leaf for inner in value for leaf in _scalars(inner)]
    return [value]


def test_a_group_spanning_two_groundings_is_refused() -> None:
    """A measurement and a judgement are not the same kind of evidence, and
    `evb-001` declares which per item precisely so "carries no refs" cannot
    be a state an item drifts into. One pair holding both means a rule
    emitted its own finding type sometimes with citations and sometimes
    without, which is that drift -- so the group cannot honestly be
    labelled."""
    # spec: api-015, evb-001
    bundle = zone()
    items = list(bundle.evidence)
    first = next(i for i in items if i.finding_type == "rf_noise_deviation")
    mixed = bundle.with_evidence(
        [
            replace(i, grounding=Grounding.DERIVED, refs=()) if i is first else i
            for i in items
        ]
    )

    with pytest.raises(EvidenceError):
        account(findings=[claim_for(mixed)], bundles=[(7, mixed)])


def test_a_group_spanning_two_data_modes_is_refused() -> None:
    """`data_mode` is per item because a fusion bundle spans both by
    definition -- but within one rule and one finding type it cannot, and the
    field tells an analyst which half of the picture is invented."""
    # spec: api-015, evb-001
    bundle = zone()
    items = list(bundle.evidence)
    first = next(i for i in items if i.finding_type == "track_continuity_gap")
    mixed = bundle.with_evidence(
        [replace(i, data_mode=DataMode.SYNTHETIC) if i is first else i for i in items]
    )

    with pytest.raises(EvidenceError):
        account(findings=[claim_for(mixed)], bundles=[(7, mixed)])


def test_the_groups_keep_the_order_the_bundle_built_them_in() -> None:
    """The builder's order is the ladder's: what was measured, then what was
    concluded from it. Sorted alphabetically, a verdict would lead its own
    evidence."""
    # spec: api-015, evb-001
    bundle = fault()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    seen: list[tuple[str, str]] = []
    for item in bundle.evidence:
        pair = (item.rule_id, item.finding_type)
        if pair not in seen:
            seen.append(pair)
    assert [(g.ruleId, g.findingType) for g in claim.evidence] == seen


# ---------------------------------------------------------------- the absences


def test_each_uncertainty_crosses_with_its_kind_and_its_statement_verbatim() -> None:
    """The kind says what sort of not-knowing it is; the statement is the only
    part a person can weigh. A consumer handed the bare word
    `not_measurable` learns nothing."""
    # spec: api-015, evb-001
    bundle = fault()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    assert [(u.kind, u.statement) for u in claim.uncertainties] == [
        (u.kind.value, u.statement) for u in bundle.known_uncertainties
    ]


def test_the_kind_crosses_by_enum_member_name_and_is_never_title_cased() -> None:
    """`ai-002`'s trap: `.title()` launders any word at all into something
    that looks valid and fails a layer later, with the bundle no longer in
    hand."""
    # spec: api-015, ai-002, evb-001
    bundle = fault()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    assert claim.uncertainties[0].kind == UncertaintyKind.NOT_APPLICABLE.value
    assert claim.uncertainties[0].kind == "not_applicable"


def test_all_three_kinds_survive_as_three_values() -> None:
    """Collapsed on screen, `evb-001`'s whole organising rule is undone at the
    last boundary before a person: *never consulted*, *consulted and could
    not tell* and *looked at and found nothing* are three different
    claims."""
    # spec: api-015, evb-001
    from app.detection.bundle import Uncertainty

    bundle = fault()
    three = replace(
        bundle,
        known_uncertainties=tuple(
            Uncertainty(kind=kind, statement=f"{kind.value} happened", subject="s")
            for kind in UncertaintyKind
        ),
    )

    claim = account(findings=[claim_for(three)], bundles=[(7, three)]).explained[0]

    assert [u.kind for u in claim.uncertainties] == [k.value for k in UncertaintyKind]


def test_a_superseded_claim_crosses_outside_the_evidence_list() -> None:
    """A competing conclusion the ladder rejected. Carried among the support,
    two rules' disagreement reads as two rules' agreement -- which is
    `ai-008`'s third verdict and the error it exists to catch."""
    # spec: api-015, evb-001, ai-008, anom-013
    from app.detection.bundle import SupersededClaim

    loser = SupersededClaim(
        rule_id="SENSOR-FAULT",
        anomaly_type="possible_sensor_fault",
        claimed_by="FUSION-SPATIAL",
        reason="an earlier rule claimed this zone",
    )
    bundle = replace(zone(), superseded=(loser,))

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    assert [s.ruleId for s in claim.superseded] == ["SENSOR-FAULT"]
    assert all(g.ruleId != "SENSOR-FAULT" for g in claim.evidence)


# -------------------------------------------------------------- the exclusions


def test_observation_ids_do_not_cross() -> None:
    """Excluded by name, following `ai-004`'s rule for its egress exclusions:
    a row id is not something an analyst can act on, and the check that needs
    them is `ai-008`'s, which ran before anything was stored."""
    # spec: api-015, ai-004, evb-002
    bundle = zone()
    with_ids = bundle.with_evidence(
        [
            replace(i, observation_ids=(111222333,) if i.refs else ())
            for i in bundle.evidence
        ]
    )

    claim = account(findings=[claim_for(with_ids)], bundles=[(7, with_ids)]).explained[0]

    assert "111222333" not in json.dumps(claim.model_dump())


def test_item_details_do_not_cross() -> None:
    """Rule-internal, and anything a person needs from them the rule already
    put in its own sentence -- `power_dbm deviated by 8.40 dB at its peak`
    carries the metric and the figure both. Served, this endpoint would have
    to know what each rule's keys mean."""
    # spec: api-015
    bundle = zone()
    marked = bundle.with_evidence(
        [replace(i, details={**i.details, "probe": "zzUNIQUEzz"}) for i in bundle.evidence]
    )

    claim = account(findings=[claim_for(marked)], bundles=[(7, marked)]).explained[0]

    assert "zzUNIQUEzz" not in json.dumps(claim.model_dump())


def test_an_aircraft_crosses_as_the_pseudonym_the_store_holds() -> None:
    """The substitution is the DAL's at ingest, so this endpoint holds no seed
    and performs no lookup. NFR-405 is satisfied for a screenshot of the
    panel because what is on it was never the real identifier."""
    # spec: api-015, NFR-405, dal-003
    bundle = zone()

    claim = account(findings=[claim_for(bundle)], bundles=[(7, bundle)]).explained[0]

    sources = group_for(claim, ("TRACK-GAP", "track_continuity_gap")).sources
    assert sources
    assert all(source.startswith("AC-") for source in sources)


def test_the_payload_names_no_scenario_type() -> None:
    """`api-009`, over the serialised payload and across all five arms,
    because `api-012` learned that a check on one field only ever proves the
    field somebody thought of."""
    # spec: api-015, api-009, api-012
    bundle = zone()

    got = account(findings=[claim_for(bundle)], bundles=[(7, bundle)])
    body = json.dumps(got.model_dump()).lower()

    for scenario_type in ScenarioType:
        assert scenario_type.value not in body


def test_the_route_builds_no_bundle() -> None:
    """`anom-016` records that the detection pass does not fire per request
    and that the baseline, at 11.2 s, is the reason. Serving a bundle built
    under current settings beside findings stored under the recorded ones
    would be two sources for one event.

    Parsed rather than searched: a comment explaining the rule would satisfy
    a text scan, which this repository has had to correct twice.
    """
    # spec: api-015, anom-016, api-012
    reached: set[str] = set()
    for module in ("app/api/v1/operational_picture.py", "app/api/v1/schemas/evidence.py"):
        tree = ast.parse((BACKEND_ROOT / module).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                reached |= {f"{node.module}.{alias.name}" for alias in node.names}
            elif isinstance(node, ast.Import):
                reached |= {alias.name for alias in node.names}

    # The *builder*, not the module: the shape has to be imported to be
    # served, and `measurements/README.md`'s own lesson is that forbidding a
    # mention rather than a use catches legitimate code. Spelled as the two
    # names a build would have to reach.
    assert "app.detection.bundle.build_bundles" not in reached
    assert not any(name.startswith("app.detection.chain") for name in reached)


# ------------------------------------------------------------------- the route


def _client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    return TestClient(app)


def _insert_run(engine: Engine, run_id: int, *, examined: bool) -> None:
    with engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO scenario_runs "
                "(id, scenario_type, parameters, seed, started_at, completed_at, "
                " detection_pass_at, detection_policy) "
                "VALUES (:id, 'gnss-degradation', '{}'::jsonb, 42, now(), now(), "
                " :examined, :policy)"
            ),
            {
                "id": run_id,
                "examined": datetime.now(UTC) if examined else None,
                "policy": json.dumps({"rf": {"threshold": 6.0}}) if examined else None,
            },
        )
        connection.commit()


@pytest.fixture
def store(migrated_database: Engine) -> Engine:
    """Head, with the seeded run removed: each test states its own hours."""
    with migrated_database.connect() as connection:
        connection.execute(text("DELETE FROM observations"))
        connection.execute(text("DELETE FROM scenario_runs"))
        connection.commit()
    return migrated_database


@pytest.mark.database
@requires_database
def test_an_hour_no_pass_examined_is_null(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`api-012`'s distinction at a second endpoint: whether anybody looked is
    answered by the presence of the account and never by a number in it. An
    unexamined hour served as three empty lists is a quiet hour."""
    # spec: api-015, api-012, anom-008, anom-015
    _insert_run(store, 1, examined=False)

    with _client(store, monkeypatch) as client:
        response = client.get(f"{EVIDENCE_PATH}?run=1")

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.database
@requires_database
def test_an_examined_quiet_hour_is_three_empty_lists_and_not_null(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-015, anom-008
    _insert_run(store, 1, examined=True)

    with _client(store, monkeypatch) as client:
        body = client.get(f"{EVIDENCE_PATH}?run=1").json()

    assert body == {"runId": 1, "explained": [], "unexplained": [], "unclaimed": []}


@pytest.mark.database
@requires_database
def test_an_unknown_run_is_refused_and_never_served_the_newest_hour(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`api-013`'s sharpest failure case, at a second endpoint: silently
    serving a different hour from the one asked for is indistinguishable from
    the feature working, and is what 'default to the latest' does."""
    # spec: api-015, api-013
    _insert_run(store, 1, examined=True)

    with _client(store, monkeypatch) as client:
        response = client.get(f"{EVIDENCE_PATH}?run=999")

    assert response.status_code == 404
    assert "999" in response.text


@pytest.mark.database
@requires_database
def test_a_non_integer_run_is_refused(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # spec: api-015, api-013, api-007
    _insert_run(store, 1, examined=True)

    with _client(store, monkeypatch) as client:
        response = client.get(f"{EVIDENCE_PATH}?run=newest")

    assert response.status_code == 422


@pytest.mark.database
@requires_database
def test_no_parameter_serves_the_hour_the_picture_serves(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One policy for "which hour is current", not two: `db-007` prefers a run
    known to have finished, and two endpoints answering that differently would
    show a panel belonging to another hour."""
    # spec: api-015, api-013, db-007
    _insert_run(store, 1, examined=True)
    _insert_run(store, 2, examined=True)

    with _client(store, monkeypatch) as client:
        evidence = client.get(EVIDENCE_PATH).json()
        picture = client.get("/api/v1/operational-picture").json()

    assert evidence["runId"] == int(picture["scenario"]["id"])


@pytest.mark.database
@requires_database
def test_an_empty_store_is_null_rather_than_a_refusal(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`api-002`'s argument: a screen that cannot render before the first run
    is a screen nobody can develop against. With no hour at all there is
    nothing that could have been examined."""
    # spec: api-015, api-002
    with _client(store, monkeypatch) as client:
        response = client.get(EVIDENCE_PATH)

    assert response.status_code == 200
    assert response.json() is None
