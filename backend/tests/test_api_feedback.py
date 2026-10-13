"""The analyst's verdict. Spec: api-005, amended 2026-10-13.

An analyst gives one of four verdicts on the explanation under review, with
an optional note. The verdict is appended to the history and the status
becomes the mapping of the latest verdict, both in one transaction, and the
reply is the explanation as the store now holds it, so the screen never shows
its own guess (`fbk-001`'s failure case).

The mapping, pinned (qa.md 165):

    confirm             -> Confirmed
    reject              -> Rejected
    false-positive      -> Rejected   (the verdict row keeps false-positive)
    needs-more-evidence -> Under review

Inconclusive stays in the stored set and nothing produces it.

Four kinds of test: contract parity, the request's validation, the store
write (one transaction, the database's own CHECK), and the endpoint.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.db.hypotheses import ReviewStatus
from app.db.migrations import alembic_config
from app.main import app
from tests.conftest import requires_database
from tests.contracts import contract_paths, union_members
from tests.contracts import interfaces as _interfaces
from tests.contracts import read_contract as _read
from tests.test_api_hypotheses import screen  # noqa: F401 -- a fixture
from tests.test_db_hypotheses import neighbours  # noqa: F401 -- a fixture

CONTRACT_PATHS = contract_paths("hypotheses.ts")
PREVIOUS = "0010_campaign_ordinal"
CONSTRAINT = "analyst_feedback_verdict_known"

MAPPING = {
    "confirm": "Confirmed",
    "reject": "Rejected",
    "false-positive": "Rejected",
    "needs-more-evidence": "Under review",
}


def _store() -> Any:
    """Imported late, so a missing name fails each test rather than the file."""
    from app.db import hypotheses

    return hypotheses


def _schemas() -> Any:
    from app.api.v1.schemas import hypotheses

    return hypotheses


def _status(engine: Engine, row: int) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(
                text("SELECT status FROM hypotheses WHERE id = :id"), {"id": row}
            ).scalar_one()
        )


def _feedback(engine: Engine, row: int) -> list[tuple[str, str | None]]:
    with engine.connect() as connection:
        return [
            (r.verdict, r.note)
            for r in connection.execute(
                text(
                    "SELECT verdict, note FROM analyst_feedback "
                    "WHERE hypothesis_id = :id ORDER BY created_at, id"
                ),
                {"id": row},
            )
        ]


def _post(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, row: int, body: Any
) -> tuple[int, Any]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        response = client.post(f"/api/v1/hypotheses/{row}/feedback", json=body)
    return response.status_code, response.json()


def _get(engine: Engine, monkeypatch: pytest.MonkeyPatch, row: int) -> Any:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        return client.get(f"/api/v1/hypotheses/{row}").json()


# --------------------------------------------------------------- contract parity


def test_the_request_shape_and_its_model_carry_the_same_fields() -> None:
    # spec: api-005 -- declared once per language, compared in both directions.
    declared = _interfaces(_read(CONTRACT_PATHS))

    assert "VerdictRequest" in declared
    assert set(declared["VerdictRequest"]) == set(
        _schemas().VerdictRequest.model_fields
    )
    assert declared["VerdictRequest"]["verdict"] == "Verdict"


def test_the_verdict_union_is_the_backends_verdict_set() -> None:
    # spec: api-005 -- exactly four, mirrored and parity-checked.
    source = _read(CONTRACT_PATHS)

    assert set(union_members(source, "Verdict")) == {
        v.value for v in _store().Verdict
    }
    assert set(MAPPING) == {v.value for v in _store().Verdict}


def test_a_stored_verdict_is_typed_by_the_union_on_both_sides() -> None:
    # spec: api-005 -- AnalystVerdict.verdict narrows from a string.
    declared = _interfaces(_read(CONTRACT_PATHS))

    assert declared["AnalystVerdict"]["verdict"] == "Verdict"
    assert _schemas().AnalystVerdict.model_fields["verdict"].annotation is (
        _store().Verdict
    )


# ------------------------------------------------------------------ the mapping


def test_each_verdict_maps_to_its_pinned_status() -> None:
    # spec: api-005 (1)
    store = _store()

    assert {v.value: s.value for v, s in store.VERDICT_STATUS.items()} == MAPPING


def test_no_verdict_produces_inconclusive_and_it_stays_a_status() -> None:
    # spec: api-005 (1) -- kept in the stored set, unused.
    store = _store()

    assert ReviewStatus.INCONCLUSIVE not in store.VERDICT_STATUS.values()
    assert ReviewStatus("Inconclusive") is ReviewStatus.INCONCLUSIVE


# ------------------------------------------------------------------ the request


@pytest.mark.parametrize("verdict", sorted(MAPPING))
def test_each_verdict_is_accepted_with_no_note(verdict: str) -> None:
    # spec: api-005 -- the note is optional.
    request = _schemas().VerdictRequest(verdict=verdict)

    assert request.verdict.value == verdict
    assert request.note is None


@pytest.mark.parametrize("note", ["", "   ", "\n\t "])
def test_an_empty_or_blank_note_is_stored_as_none(note: str) -> None:
    # spec: api-005 -- an empty or whitespace-only note is no note.
    assert _schemas().VerdictRequest(verdict="confirm", note=note).note is None


def test_a_note_of_2000_characters_is_accepted_and_kept_verbatim() -> None:
    # spec: api-005 -- the limit is inclusive.
    note = "x" * 2000

    assert _schemas().VerdictRequest(verdict="reject", note=note).note == note


@pytest.mark.parametrize(
    "body",
    [
        {"verdict": "confirmed"},
        {"verdict": "Confirm"},
        {"verdict": "inconclusive"},
        {"verdict": ""},
        {"note": "no verdict at all"},
        {"verdict": "confirm", "note": "x" * 2001},
    ],
)
def test_an_unrecognised_or_missing_verdict_or_long_note_is_refused(
    body: dict[str, Any],
) -> None:
    # spec: api-005 -- failure case: validated before anything is written.
    with pytest.raises(ValidationError):
        _schemas().VerdictRequest(**body)


# -------------------------------------------------------------------- the store


@pytest.mark.database
@requires_database
@pytest.mark.parametrize("verdict", sorted(MAPPING))
def test_a_verdict_is_appended_and_sets_its_status(
    migrated_database: Engine,
    factory: sessionmaker,
    screen: dict[str, int],  # noqa: F811
    verdict: str,
) -> None:
    # spec: api-005 (1), (3)
    store = _store()
    row = screen["reviewed"]

    store.record_verdict(factory, row, store.Verdict(verdict), "a note")

    assert _status(migrated_database, row) == MAPPING[verdict]
    assert _feedback(migrated_database, row) == [(verdict, "a note")]


@pytest.mark.database
@requires_database
def test_the_latest_verdict_sets_the_status_and_none_is_lost(
    migrated_database: Engine,
    factory: sessionmaker,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 (2) -- an analyst may change their mind; the history stays.
    store = _store()
    row = screen["reviewed"]

    store.record_verdict(factory, row, store.Verdict.CONFIRM, None)
    store.record_verdict(factory, row, store.Verdict.NEEDS_MORE_EVIDENCE, "wait")
    store.record_verdict(factory, row, store.Verdict.FALSE_POSITIVE, None)

    assert _status(migrated_database, row) == "Rejected"
    assert _feedback(migrated_database, row) == [
        ("confirm", None),
        ("needs-more-evidence", "wait"),
        ("false-positive", None),
    ]


@pytest.mark.database
@requires_database
def test_a_verdict_on_one_row_leaves_every_other_row_alone(
    migrated_database: Engine,
    factory: sessionmaker,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 -- the other rows of the same conclusion are not touched.
    store = _store()

    store.record_verdict(factory, screen["reviewed"], store.Verdict.REJECT, None)

    for other in ("trial", "second_ask", "baseline", "fell_back"):
        assert _status(migrated_database, screen[other]) == "New"
        assert _feedback(migrated_database, screen[other]) == []


@pytest.mark.database
@requires_database
def test_a_verdict_for_an_unknown_row_is_refused_and_writes_nothing(
    migrated_database: Engine,
    factory: sessionmaker,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 -- failure case.
    store = _store()

    with pytest.raises(store.HypothesisWriteError):
        store.record_verdict(factory, 999_999, store.Verdict.CONFIRM, None)

    with migrated_database.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM analyst_feedback")
        ).scalar_one() == 0


@pytest.mark.database
@requires_database
@pytest.mark.parametrize(
    "table,event", [("hypotheses", "UPDATE"), ("analyst_feedback", "INSERT")]
)
def test_a_write_failing_midway_leaves_status_and_history_as_they_were(
    migrated_database: Engine,
    factory: sessionmaker,
    screen: dict[str, int],  # noqa: F811
    table: str,
    event: str,
) -> None:
    # spec: api-005 (3) -- failure case: both or neither, whichever half fails.
    store = _store()
    row = screen["reviewed"]
    with migrated_database.connect() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION refuse() RETURNS trigger AS "
                "$$ BEGIN RAISE EXCEPTION 'refused for the test'; END $$ "
                "LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER refuse BEFORE {event} ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION refuse()"
            )
        )
        connection.commit()
    try:
        with pytest.raises(Exception, match="refused for the test"):
            store.record_verdict(factory, row, store.Verdict.CONFIRM, "lost")
    finally:
        with migrated_database.connect() as connection:
            connection.execute(text(f"DROP TRIGGER refuse ON {table}"))
            connection.execute(text("DROP FUNCTION refuse()"))
            connection.commit()

    assert _status(migrated_database, row) == "New"
    assert _feedback(migrated_database, row) == []


@pytest.mark.database
@requires_database
def test_the_database_refuses_a_verdict_outside_the_set(
    migrated_database: Engine,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 (5) -- the CHECK holds the set, whoever writes.
    with migrated_database.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO analyst_feedback (hypothesis_id, verdict) "
                "VALUES (:h, 'confirmed')"
            ),
            {"h": screen["reviewed"]},
        )


@pytest.mark.database
@requires_database
def test_the_verdict_constraint_is_reversible(migrated_database: Engine) -> None:
    # spec: api-005 (5) -- migration 0011, the target revision named.
    config = alembic_config()
    config.set_main_option(
        "sqlalchemy.url", migrated_database.url.render_as_string(hide_password=False)
    )

    def present() -> bool:
        with migrated_database.connect() as connection:
            return bool(
                connection.execute(
                    text("SELECT count(*) FROM pg_constraint WHERE conname = :n"),
                    {"n": CONSTRAINT},
                ).scalar_one()
            )

    assert present()
    command.downgrade(config, PREVIOUS)
    assert not present()
    command.upgrade(config, "head")
    assert present()


# ------------------------------------------------------------------ the endpoint


@pytest.mark.database
@requires_database
def test_the_reply_is_the_explanation_as_the_store_now_holds_it(
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 -- the same shape as GET, the new verdict last; a reload
    # agrees, because it was written rather than guessed.
    row = screen["reviewed"]

    status, body = _post(
        migrated_database, monkeypatch, row, {"verdict": "confirm", "note": "seen"}
    )

    assert status == 200
    assert body["id"] == row
    assert body["status"] == "Confirmed"
    assert [(v["verdict"], v["note"]) for v in body["verdicts"]] == [
        ("confirm", "seen")
    ]
    assert body == _get(migrated_database, monkeypatch, row)


@pytest.mark.database
@requires_database
def test_false_positive_is_rejected_and_keeps_its_own_verdict(
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 (1)
    status, body = _post(
        migrated_database,
        monkeypatch,
        screen["reviewed"],
        {"verdict": "false-positive"},
    )

    assert status == 200
    assert body["status"] == "Rejected"
    assert body["verdicts"][-1]["verdict"] == "false-positive"
    assert body["verdicts"][-1]["note"] is None


@pytest.mark.database
@requires_database
@pytest.mark.parametrize(
    "body",
    [
        {"verdict": "confirmed"},
        {"note": "no verdict"},
        {"verdict": "reject", "note": "x" * 2001},
    ],
)
def test_a_refused_request_writes_nothing(
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    screen: dict[str, int],  # noqa: F811
    body: dict[str, Any],
) -> None:
    # spec: api-005 -- failure case: 422, no feedback row, no status change.
    row = screen["reviewed"]

    status, _ = _post(migrated_database, monkeypatch, row, body)

    assert status == 422
    assert _status(migrated_database, row) == "New"
    assert _feedback(migrated_database, row) == []


@pytest.mark.database
@requires_database
def test_an_unknown_explanation_is_not_found(
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 -- failure case.
    status, body = _post(migrated_database, monkeypatch, 999_999, {"verdict": "reject"})

    assert status == 404
    assert "999999" in body["detail"]


@pytest.mark.database
@requires_database
@pytest.mark.parametrize("which", ["trial", "second_ask", "baseline"])
def test_a_row_that_is_not_reviewable_takes_no_verdict(
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    screen: dict[str, int],  # noqa: F811
    which: str,
) -> None:
    # spec: api-005 (4) -- failure case: 409, nothing written, so a verdict
    # and a blind score always refer to the same text.
    row = screen[which]

    status, body = _post(migrated_database, monkeypatch, row, {"verdict": "confirm"})

    assert status == 409
    assert "reviewable" in body["detail"]
    assert _status(migrated_database, row) == "New"
    assert _feedback(migrated_database, row) == []


@pytest.mark.database
@requires_database
def test_a_reviewable_row_that_fell_back_takes_a_verdict(
    migrated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    screen: dict[str, int],  # noqa: F811
) -> None:
    # spec: api-005 (4) -- reviewable is about what was asked, not who answered.
    status, body = _post(
        migrated_database,
        monkeypatch,
        screen["fell_back"],
        {"verdict": "needs-more-evidence"},
    )

    assert status == 200
    assert body["status"] == "Under review"
