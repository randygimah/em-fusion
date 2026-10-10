"""Where evidence bundles are resolved and stored. Spec: evb-002.

All the SQL for `evidence_bundles`, and the only module above the builder
that knows the table exists -- FR-904's rule about where SQL lives, applied
here as it is to `observations` and `detection_findings`.

**Resolution is the point, not storage.** A bundle is the only thing the AI
layer ever receives, and `ai-008` checks a model's citations against it. A
citation is only checkable if the thing it cites exists, so every item is
looked up before any bundle is written. Three ways that fails and all three
are refusals:

*Zero rows* -- the bundle asserts something it cannot show. Measured, and
not hypothetical: before `anom-010` carried `observed_at`, 91 of 1,021 real
citations landed on a frozen-position window start, an instant reconstructed
from the reported staleness at which nothing was ever recorded.

*More than one row* -- worse, because the bundle would cite whichever row
the heap returned first and nothing anywhere would say so. This is the
unordered-result failure this project has now recorded three times.
`evidence_ref_uniqueness.py` measured the coordinate unique across 20.7M
rows, but uniqueness is a property of the corpus rather than a constraint
the schema enforces, so it is checked rather than assumed.

*A shape the resolver does not know* -- refused by name. `from_track_cluster`
emits `{aircraft_id}` with no time at all, which as a predicate matches
every report that aircraft made; a resolver assembled from whatever keys
happened to be present would build an *empty* predicate for an empty ref and
match the entire run.

**Queries are batched and scoped.** One query per coordinate shape per
bundle rather than one per citation: `db-010`'s index narrows to the run and
nothing narrows further, so the filter is paid once instead of once per ref
-- 10.5 ms against 194.5 ms at the median, measured over 24 real bundles in
`bundle_ref_cost.py`. Every query is scoped to the scenario run, because the
uniqueness above is uniqueness *within* one run and the same coordinate
exists in all 300 of them.

**The write replaces, per run**, following `db-008`. A bundle is derived
from findings which are derived from the seed, so appending would leave a
superseded bundle beside a current one with nothing on either to say which
is which. Writing an empty set therefore clears what was there -- the same
argument at zero, and the case a run re-detected as quiet produces.

**And that replace has one thing it may not touch** (`db-011`). It deletes
before it inserts, `hypotheses.bundle_id` is declared ON DELETE CASCADE,
and that column is the only link the `hypotheses` table has to a run --
there is no `scenario_run_id` on it. So replacing a cited run's bundles
deletes the hypothesis rows citing them with no error anywhere: the DELETE
succeeds, the cascade fires, and the damage is visible only as rows that
are gone. On the store of record that is 155 rows on 20 bundles across runs
102-175, which is `eval-004`'s pre-registered sample and the one population
here that cannot be regenerated. `_refuse_if_cited` is checked before
resolution and decided from the store; deleting a scenario run still
cascades, which is the point of putting the refusal here rather than at the
foreign key.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session, sessionmaker

from app.dal.models import DataMode, Location
from app.detection.bundle import (
    BundleError,
    EvidenceBundle,
    EvidenceItem,
    Grounding,
    SupersededClaim,
    Uncertainty,
    UncertaintyKind,
)

#: WGS 84, the SRID every geometry column in `db-001` declares.
SRID = 4326

#: The two coordinate shapes the rules emit, as exact key sets. A closed
#: set matched by name: a ref is one of these or it is refused. Note that
#: the two spell the time differently -- `anom-001` writes `timestamp` and
#: `anom-010` writes `at` -- so a resolver reading `timestamp` alone misses
#: every track citation while appearing to work.
RF_REF_KEYS = frozenset({"sensor_id", "channel_index", "timestamp"})
TRACK_REF_KEYS = frozenset({"aircraft_id", "at"})


class ResolutionError(BundleError):
    """A citation that does not identify exactly one stored observation.

    A `BundleError` because the outcome is the same as any other malformed
    bundle: nothing is emitted. A caller catching bundle problems catches
    this without knowing the storage layer exists.
    """


class CitedBundleError(BundleError):
    """A stored bundle another row cites, handed to a stage that replaces.

    A `BundleError` so a caller catching bundle problems catches it, and
    deliberately **not** a `ResolutionError`: that one means a citation does
    not identify exactly one observation, which is a defect in the bundle,
    and `measurements/corpus/bundle_end_to_end.py` catches it by name to
    report a traceability failure. A protected population reported as a
    traceability defect sends the reader to the wrong half of the system.
    """


def citing_hypotheses(
    session_factory: sessionmaker[Session], run_id: int
) -> dict[int, int]:
    """Which of this run's bundles a hypothesis cites, and how many cite each.

    **Counts rather than a boolean**, for two reasons. The refusal has to
    print the number, because a reader meeting it must tell a protected
    population from a bug and the two look identical until the numbers are
    there -- `conftest`'s own argument for the database guard's named
    counts. And one bundle legitimately carries several hypotheses: a model
    arm's answer and the template that replaced it after a grounding
    failure, which is exactly why `db-002` appends rather than replaces.

    A bundle nothing cites is **omitted and never carried as a zero**. The
    mapping is the set of reasons to refuse, so an entry meaning "no
    reason" is one an implementation can read as a reason by testing for
    presence -- and `if cited:` is how the guard below asks.

    Ordered by bundle id. Not because anything downstream needs it, but
    because this reaches a human in an error message, and an unordered
    result takes its order from the heap -- which this repository has had
    to fix three times.
    """
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "SELECT h.bundle_id AS bundle_id, count(*) AS citations "
                    "FROM hypotheses h "
                    "  JOIN evidence_bundles b ON b.id = h.bundle_id "
                    "WHERE b.scenario_run_id = :run "
                    "GROUP BY h.bundle_id "
                    "ORDER BY h.bundle_id"
                ),
                {"run": run_id},
            )
            .mappings()
            .all()
        )
    return {int(row["bundle_id"]): int(row["citations"]) for row in rows}


def _ewkt(location: Location) -> str:
    """A point as EWKT text, longitude first.

    Longitude is X and latitude is Y and the two are the same kind of
    number, so a transposition produces valid geometry in the wrong place
    and no error anywhere. Written once, as `app/db/findings.py` does, and
    text rather than a `WKTElement` for the reason recorded there: these
    statements are textual, so the driver sees a bare parameter and cannot
    adapt it.
    """
    return f"SRID={SRID};POINT({location.lon} {location.lat})"


# ------------------------------------------------------------------ resolution


def resolve_bundles(
    session_factory: sessionmaker[Session],
    bundles: Sequence[EvidenceBundle],
) -> tuple[EvidenceBundle, ...]:
    """Every citation looked up, or nothing.

    Returns the same bundles with each OBSERVED item carrying the rows its
    refs resolved to, in the order they were cited -- a set would lose which
    id answers which citation, and `ai-008` checks a citation rather than a
    bundle.
    """
    return tuple(_resolve_one(session_factory, bundle) for bundle in bundles)


def _resolve_one(
    session_factory: sessionmaker[Session], bundle: EvidenceBundle
) -> EvidenceBundle:
    rf: list[tuple[int, int, dict[str, Any]]] = []
    track: list[tuple[int, int, dict[str, Any]]] = []

    for position, item in enumerate(bundle.evidence):
        if item.grounding is Grounding.DERIVED:
            # A judgement has no row, so it is not queried for one. The
            # declaration is what makes this safe: an item cannot reach here
            # by having forgotten its refs, because `EvidenceItem` refuses
            # an OBSERVED item that cites nothing.
            continue
        for index, ref in enumerate(item.refs):
            keys = frozenset(ref)
            if keys == RF_REF_KEYS:
                rf.append((position, index, ref))
            elif keys == TRACK_REF_KEYS:
                track.append((position, index, ref))
            else:
                raise ResolutionError(
                    f"evidence item {item.source!r} cites {sorted(keys)}, which is "
                    f"neither {sorted(RF_REF_KEYS)} nor {sorted(TRACK_REF_KEYS)}. "
                    "An unknown shape is refused rather than resolved on whatever "
                    "keys it happens to carry, because a predicate built that way "
                    "matches too much: an aircraft with no time matches every "
                    "report it made, and an empty ref matches the whole run."
                )

    found: dict[tuple[int, int], list[int]] = {}
    # No citations, no transaction. A bundle of pure judgements -- which the
    # corpus does not produce but the builder can -- must not need a
    # database to be resolved, and every refusal decidable from the bundle
    # alone has already been raised above, before any connection was opened.
    if rf or track:
        with session_factory.begin() as session:
            _match_rf(session, bundle.scenario_run_id, rf, found)
            _match_track(session, bundle.scenario_run_id, track, found)

    resolved: list[EvidenceItem] = []
    for position, item in enumerate(bundle.evidence):
        if item.grounding is Grounding.DERIVED:
            resolved.append(item)
            continue
        ids: list[int] = []
        for index, ref in enumerate(item.refs):
            matched = found.get((position, index), [])
            if len(matched) != 1:
                raise _miss(bundle, item, ref, matched)
            ids.append(matched[0])
        resolved.append(replace(item, observation_ids=tuple(ids)))

    return bundle.with_evidence(resolved)


def _miss(
    bundle: EvidenceBundle,
    item: EvidenceItem,
    ref: dict[str, Any],
    matched: Sequence[int],
) -> ResolutionError:
    """The refusal, phrased so the log says which of the two failures it is."""
    where = f"run {bundle.scenario_run_id}, {bundle.rule_id} on " f"{bundle.subject!r}"
    if not matched:
        return ResolutionError(
            f"{where}: evidence item {item.source!r} cites {ref}, and there is "
            "no stored observation at that coordinate. A bundle whose evidence "
            "cannot be looked up asserts something it cannot show, and the "
            "grounding check downstream would have nothing to resolve it "
            "against."
        )
    return ResolutionError(
        f"{where}: evidence item {item.source!r} cites {ref}, which matches "
        f"{len(matched)} stored observations. That is worse than matching none: "
        "the bundle would carry whichever row came back first, and nothing "
        "anywhere would record that the citation was ambiguous."
    )


def _match_rf(
    session: Session,
    run_id: int,
    refs: Sequence[tuple[int, int, dict[str, Any]]],
    found: dict[tuple[int, int], list[int]],
) -> None:
    """Every RF citation in one query, scoped to the run."""
    if not refs:
        return
    values = ", ".join(
        f"(:s{n}, :c{n}, CAST(:t{n} AS timestamptz))" for n in range(len(refs))
    )
    params: dict[str, Any] = {"run": run_id}
    for n, (_, _, ref) in enumerate(refs):
        params[f"s{n}"] = ref["sensor_id"]
        params[f"c{n}"] = ref["channel_index"]
        # Compared as the stored string without normalising: the ISO round
        # trip was measured exact on 2,000 sampled observations.
        params[f"t{n}"] = ref["timestamp"]

    rows = (
        session.execute(
            text(
                "SELECT id, payload->>'sensor_id' AS sensor_id, "
                "  (payload->>'channel_index')::int AS channel_index, timestamp "
                "FROM observations "
                "WHERE scenario_run_id = :run AND observation_type = 'rf' "
                "  AND (payload->>'sensor_id', (payload->>'channel_index')::int, "
                f"      timestamp) IN ({values})"
            ),
            params,
        )
        .mappings()
        .all()
    )

    by_coordinate: dict[tuple[str, int, datetime], list[int]] = {}
    for row in rows:
        key = (row["sensor_id"], row["channel_index"], row["timestamp"])
        by_coordinate.setdefault(key, []).append(int(row["id"]))
    for position, index, ref in refs:
        key = (
            ref["sensor_id"],
            int(ref["channel_index"]),
            datetime.fromisoformat(ref["timestamp"]),
        )
        found[(position, index)] = by_coordinate.get(key, [])


def _match_track(
    session: Session,
    run_id: int,
    refs: Sequence[tuple[int, int, dict[str, Any]]],
    found: dict[tuple[int, int], list[int]],
) -> None:
    """Every track citation in one query, scoped to the run."""
    if not refs:
        return
    values = ", ".join(f"(:a{n}, CAST(:t{n} AS timestamptz))" for n in range(len(refs)))
    params: dict[str, Any] = {"run": run_id}
    for n, (_, _, ref) in enumerate(refs):
        params[f"a{n}"] = ref["aircraft_id"]
        params[f"t{n}"] = ref["at"]

    rows = (
        session.execute(
            text(
                "SELECT id, payload->>'aircraft_id' AS aircraft_id, timestamp "
                "FROM observations "
                "WHERE scenario_run_id = :run AND observation_type = 'track' "
                f"  AND (payload->>'aircraft_id', timestamp) IN ({values})"
            ),
            params,
        )
        .mappings()
        .all()
    )

    by_coordinate: dict[tuple[str, datetime], list[int]] = {}
    for row in rows:
        key = (row["aircraft_id"], row["timestamp"])
        by_coordinate.setdefault(key, []).append(int(row["id"]))
    for position, index, ref in refs:
        key = (ref["aircraft_id"], datetime.fromisoformat(ref["at"]))
        found[(position, index)] = by_coordinate.get(key, [])


# ----------------------------------------------------------------- persistence


def _refuse_if_cited(
    session_factory: sessionmaker[Session], scenario_run_id: int
) -> None:
    """Refuse to replace a run's bundles while a hypothesis cites one. db-011.

    **Before resolution, not merely before the write.** `evb-002` resolves
    every citation with a query before it will store anything, which is the
    whole point of that item -- and a refusal decidable from the store
    alone must not pay for it first. Asserted by which error comes back
    when a cited run is handed an unresolvable bundle.

    **Decided from the store and never from an argument.** No `force`, no
    allowlist, no module-level set of protected run ids: `api-013` rejected
    exactly that for the hour chooser, on the grounds that it replaces a
    structural guarantee with a convention somebody has to know. The fact
    lives in `hypotheses.bundle_id`, so a twenty-first cited bundle
    protects itself.

    **The unit of refusal is the run**, because the unit of the delete is
    the run. Writing the uncited bundles and skipping the cited one would
    delete both and insert one, which is the damage this prevents wearing
    the appearance of a partial success.

    **Writing an empty set is the same act.** `evb-002` makes a zero-bundle
    write clear what was there -- the replace rule at zero, and the state a
    run re-detected as quiet produces -- which on a cited run is the
    identical cascade with nothing inserted afterwards. A guard asserted
    only over a non-empty list would leave the worst case open.
    """
    cited = citing_hypotheses(session_factory, scenario_run_id)
    if not cited:
        return
    total = sum(cited.values())
    rows = "is" if total == 1 else "es"
    names = ", ".join(str(bundle_id) for bundle_id in cited)
    raise CitedBundleError(
        f"refusing to replace the evidence bundles of run {scenario_run_id}: "
        f"{total} hypothes{rows} cite {len(cited)} of them ({names}). The "
        "write replaces per run (`db-008`), `hypotheses.bundle_id` is "
        "declared ON DELETE CASCADE, and that column is the only link the "
        f"`hypotheses` table has to a run -- so this would delete {total} "
        f"stored hypothes{rows} and raise nothing anywhere. Those rows cannot "
        "be regenerated: a model call consumed money and produced one "
        "specific response, which is why `db-002` appends rather than "
        "replaces. Deleting the scenario run itself still cascades, "
        "deliberately; what is refused here is replacement by a "
        "derived-data stage."
    )


def save_bundles(
    session_factory: sessionmaker[Session],
    *,
    scenario_run_id: int,
    bundles: Sequence[EvidenceBundle],
) -> tuple[EvidenceBundle, ...]:
    """Resolve every bundle for this run, then replace the run's bundles.

    **Atomicity is per run, not per bundle.** Resolution happens in full
    before anything is written, so a single unresolvable citation leaves the
    database exactly as it was -- which is this item's "must not persist a
    partial bundle" read at the only unit where it means anything. The write
    is then one transaction, so a failure leaves the previous set standing
    rather than deleting it and failing to insert.
    """
    for bundle in bundles:
        if bundle.scenario_run_id != scenario_run_id:
            raise ResolutionError(
                f"a bundle for run {bundle.scenario_run_id} was handed to a save "
                f"for run {scenario_run_id}. Writing it would file one run's "
                "event under another's id, and the replace below would delete it "
                "the next time that run was generated."
            )

    _refuse_if_cited(session_factory, scenario_run_id)

    resolved = resolve_bundles(session_factory, bundles)
    rows = [_row(bundle) for bundle in resolved]

    with session_factory.begin() as session:
        session.execute(
            text("DELETE FROM evidence_bundles WHERE scenario_run_id = :run"),
            {"run": scenario_run_id},
        )
        if rows:
            session.execute(
                text(
                    "INSERT INTO evidence_bundles "
                    "(scenario_run_id, anomaly_type, rule_id, subject, "
                    " started_at, ended_at, affected_channels, evidence, "
                    " known_uncertainties, superseded, affected_area) "
                    "VALUES (:scenario_run_id, :anomaly_type, :rule_id, :subject, "
                    " :started_at, :ended_at, :affected_channels, :evidence, "
                    " :known_uncertainties, :superseded, "
                    " ST_GeomFromEWKT(:affected_area))"
                ),
                rows,
            )
    return resolved


def bundles_for_run(
    session_factory: sessionmaker[Session], run_id: int
) -> list[EvidenceBundle]:
    """Every bundle for one run, oldest first.

    An empty result is an empty list. A run with no bundles is the ordinary
    outcome -- `anom-008` requires it of every quiet run -- not an error and
    not a null for the caller to remember to test.
    """
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "SELECT scenario_run_id, anomaly_type, rule_id, subject, "
                    "  started_at, ended_at, affected_channels, evidence, "
                    "  known_uncertainties, superseded, "
                    "  ST_Y(affected_area) AS lat, ST_X(affected_area) AS lon "
                    "FROM evidence_bundles "
                    "WHERE scenario_run_id = :run "
                    "ORDER BY started_at, subject, id"
                ),
                {"run": run_id},
            )
            .mappings()
            .all()
        )
    return [_bundle(row) for row in rows]


def stored_bundles_for_run(
    session_factory: sessionmaker[Session], run_id: int
) -> list[tuple[int, EvidenceBundle]]:
    """Every bundle for one run, each with the identity of its row.

    Beside `bundles_for_run` rather than a change to it. A hypothesis
    references the bundle it explains by id (`db-002`), and nothing exposed
    one -- a blocker found by attempting that write rather than by reading
    the schema. Changing the existing reader's return type instead would
    have touched `evb-002`'s suite and two committed measurements to add a
    value neither of them wants.
    """
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "SELECT id, scenario_run_id, anomaly_type, rule_id, subject, "
                    "  started_at, ended_at, affected_channels, evidence, "
                    "  known_uncertainties, superseded, "
                    "  ST_Y(affected_area) AS lat, ST_X(affected_area) AS lon "
                    "FROM evidence_bundles "
                    "WHERE scenario_run_id = :run "
                    "ORDER BY started_at, subject, id"
                ),
                {"run": run_id},
            )
            .mappings()
            .all()
        )
    return [(row["id"], _bundle(row)) for row in rows]


def stored_bundles_by_id(
    session_factory: sessionmaker[Session], bundle_ids: Sequence[int]
) -> dict[int, EvidenceBundle]:
    """The named bundles, each by its row id; an unknown id is simply absent.

    `api-004` reads the bundle a hypothesis explains, which may be in any run.
    """
    if not bundle_ids:
        return {}
    with session_factory.begin() as session:
        rows = (
            session.execute(
                text(
                    "SELECT id, scenario_run_id, anomaly_type, rule_id, subject, "
                    "  started_at, ended_at, affected_channels, evidence, "
                    "  known_uncertainties, superseded, "
                    "  ST_Y(affected_area) AS lat, ST_X(affected_area) AS lon "
                    "FROM evidence_bundles WHERE id = ANY(:ids)"
                ),
                {"ids": list(bundle_ids)},
            )
            .mappings()
            .all()
        )
    return {row["id"]: _bundle(row) for row in rows}


def _row(bundle: EvidenceBundle) -> dict[str, object]:
    """One bundle as the insert's parameters."""
    return {
        "scenario_run_id": bundle.scenario_run_id,
        "anomaly_type": bundle.anomaly_type,
        "rule_id": bundle.rule_id,
        "subject": bundle.subject,
        "started_at": bundle.time_window[0],
        "ended_at": bundle.time_window[1],
        "affected_channels": json.dumps(list(bundle.affected_channels)),
        "evidence": json.dumps([_item_json(item) for item in bundle.evidence]),
        "known_uncertainties": json.dumps(
            [
                {
                    "kind": uncertainty.kind.value,
                    "statement": uncertainty.statement,
                    "subject": uncertainty.subject,
                }
                for uncertainty in bundle.known_uncertainties
            ]
        ),
        "superseded": json.dumps(
            [
                {
                    "rule_id": claim.rule_id,
                    "anomaly_type": claim.anomaly_type,
                    "claimed_by": claim.claimed_by,
                    "reason": claim.reason,
                }
                for claim in bundle.superseded
            ]
        ),
        "affected_area": _ewkt(bundle.affected_area),
    }


def _item_json(item: EvidenceItem) -> dict[str, Any]:
    """One evidence item as JSON, resolved ids attached to the item itself.

    Not a join table, which was the alternative. A foreign key would
    re-guarantee exactly what resolution has just proved, observations are
    never deleted under `db-007` so it would have nothing to defend against,
    and `ai-008` needs the ids beside the citation they answer rather than
    pooled across the bundle.
    """
    return {
        "source": item.source,
        "finding": item.finding,
        "rule_id": item.rule_id,
        "finding_type": item.finding_type,
        "grounding": item.grounding.value,
        "data_mode": item.data_mode.value,
        "started_at": item.started_at.isoformat(),
        "ended_at": item.ended_at.isoformat(),
        "refs": list(item.refs),
        "details": item.details,
        "observation_ids": list(item.observation_ids),
    }


def _bundle(row: RowMapping) -> EvidenceBundle:
    return EvidenceBundle(
        scenario_run_id=row["scenario_run_id"],
        anomaly_type=row["anomaly_type"],
        rule_id=row["rule_id"],
        subject=row["subject"],
        time_window=(row["started_at"], row["ended_at"]),
        affected_area=Location(lat=row["lat"], lon=row["lon"]),
        affected_channels=tuple(row["affected_channels"]),
        evidence=tuple(_item(item) for item in row["evidence"]),
        known_uncertainties=tuple(
            Uncertainty(
                kind=UncertaintyKind(uncertainty["kind"]),
                statement=uncertainty["statement"],
                subject=uncertainty["subject"],
            )
            for uncertainty in row["known_uncertainties"]
        ),
        superseded=tuple(
            SupersededClaim(
                rule_id=claim["rule_id"],
                anomaly_type=claim["anomaly_type"],
                claimed_by=claim["claimed_by"],
                reason=claim["reason"],
            )
            for claim in row["superseded"]
        ),
    )


def _item(stored: dict[str, Any]) -> EvidenceItem:
    return EvidenceItem(
        source=stored["source"],
        finding=stored["finding"],
        rule_id=stored["rule_id"],
        finding_type=stored["finding_type"],
        grounding=Grounding(stored["grounding"]),
        data_mode=DataMode(stored["data_mode"]),
        started_at=datetime.fromisoformat(stored["started_at"]),
        ended_at=datetime.fromisoformat(stored["ended_at"]),
        refs=tuple(stored["refs"]),
        details=stored["details"],
        observation_ids=tuple(stored["observation_ids"]),
    )


__all__ = [
    "RF_REF_KEYS",
    "TRACK_REF_KEYS",
    "ResolutionError",
    "bundles_for_run",
    "resolve_bundles",
    "save_bundles",
    "stored_bundles_by_id",
    "stored_bundles_for_run",
]
