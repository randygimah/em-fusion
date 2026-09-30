"""The database tier refuses a database holding real data. Spec: ops-004.

`conftest.py` has always carried the argument for this in a comment: the
test tier is keyed on `TEST_DATABASE_URL` and **deliberately not** on
`DATABASE_URL`, so that a fixture whose first act is `DROP SCHEMA` can never
be pointed at whatever database somebody happened to have configured. Two
variables were said to make that impossible by construction rather than by
care.

They do not. They make it impossible *by convention*, and a convention is a
thing a person types. Passing the application's own database as
`TEST_DATABASE_URL` on a one-off command -- to avoid waiting for the target
that provisions a separate database -- destroyed 540 scenario runs and 20.7
million observations. This suite is that comment turned into a check.

Two checks, failing in different ways and both wanted:

**The identity check** is exact and cheap, and it catches the mistake that
was actually made. It is also the weaker of the two, because it compares
spellings: one database reached as `localhost` and as a container hostname
is two spellings of one disaster, and this check sees two different URLs.

**The population check** is the one that matters. Immediately before the
drop, the target is asked how much it is holding. A fixture creates one or
two runs; a corpus holds hundreds of runs and tens of millions of rows.
Anything in between is nobody's normal state, so the threshold is low and
the refusal names the counts it found rather than only refusing.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    MAX_FIXTURE_OBSERVATIONS,
    MAX_FIXTURE_RUNS,
    DatabaseGuardError,
    guard_population,
    same_database,
)

APP = "postgresql+psycopg://postgres:postgres@postgis:5432/em_fusion"
TEST = "postgresql+psycopg://postgres:postgres@postgis:5432/test_em_fusion"


# ------------------------------------------------------ the identity check


def test_the_application_database_is_recognised_as_itself() -> None:
    """The exact mistake: the application's own URL handed to the test tier."""
    # spec: ops-004
    assert same_database(APP, APP) is True


def test_a_separate_test_database_on_the_same_server_is_allowed() -> None:
    """`make test-backend` provisions this. Refusing it would make the guard
    useless, since the only way past would be to switch the guard off."""
    # spec: ops-004
    assert same_database(APP, TEST) is False


def test_credentials_and_driver_do_not_change_the_answer() -> None:
    """Same database, reached as a different user over a different driver, is
    still the same database. A guard comparing whole URL strings would miss
    this, and comparing whole strings is the obvious implementation."""
    # spec: ops-004
    other = "postgresql://someone:else@postgis:5432/em_fusion"
    assert same_database(APP, other) is True


def test_a_different_port_on_the_same_host_is_a_different_database() -> None:
    """Two servers on one host is an ordinary local setup."""
    # spec: ops-004
    assert same_database(APP, APP.replace(":5432/", ":5433/")) is False


# ---------------------------------------------------- the population check


def test_a_corpus_sized_database_is_refused() -> None:
    """The counts destroyed: 540 runs, 20.7M observations."""
    # spec: ops-004, db-007
    with pytest.raises(DatabaseGuardError, match="540 scenario runs"):
        guard_population(runs=540, observations=20_741_000, url=APP)


def test_the_refusal_names_what_it_found_rather_than_only_refusing() -> None:
    """A guard that says "refused" teaches nothing. One that says what it saw
    tells the reader whether they pointed at the wrong database or whether a
    test left something behind."""
    # spec: ops-004
    with pytest.raises(DatabaseGuardError) as refused:
        guard_population(runs=540, observations=20_741_000, url=APP)
    message = str(refused.value)
    assert "20,741,000" in message
    assert "em_fusion" in message


def test_an_empty_database_is_allowed() -> None:
    # spec: ops-004
    guard_population(runs=0, observations=0, url=TEST)


def test_the_rows_a_previous_test_left_are_allowed() -> None:
    """Fixtures in one session insert a run or two. Refusing those would make
    the tier unrunnable, which is the failure mode that gets a guard removed
    rather than fixed."""
    # spec: ops-004
    guard_population(runs=2, observations=6, url=TEST)


def test_the_threshold_refuses_far_below_a_corpus() -> None:
    """Set low on purpose. Nothing legitimate sits between a handful of
    fixture rows and a generated corpus, so the guard does not need to be
    tuned finely -- it needs to be nowhere near either edge."""
    # spec: ops-004
    assert MAX_FIXTURE_RUNS < 60, "far below a corpus, which is 300 runs"
    assert MAX_FIXTURE_OBSERVATIONS < 100_000, "one run alone holds tens of thousands"
    with pytest.raises(DatabaseGuardError):
        guard_population(runs=MAX_FIXTURE_RUNS + 1, observations=0, url=TEST)
    with pytest.raises(DatabaseGuardError):
        guard_population(runs=0, observations=MAX_FIXTURE_OBSERVATIONS + 1, url=TEST)


def test_the_threshold_admits_what_a_legitimate_test_writes() -> None:
    """The other side of the bracket, and the one that was missing.

    `MAX_FIXTURE_RUNS` was 20 -- exactly a batch's floor -- so a test writing one
    legitimate minimum batch, plus the run `migrated_database` seeds, left 21 and
    refused the schema drop for every database test after it in the session. The
    ceiling was checked against a corpus from above and against nothing from
    below, which is how a value can sit on an edge a comment says it is nowhere
    near. Asserted here rather than in the comment, and against the batch bounds
    themselves rather than a repeated literal.
    """
    # spec: eval-001, scn-003
    from app.pipeline import MAX_RUNS, MIN_RUNS

    # One shared-fixture run beside the largest batch a test could legitimately
    # write. Anything at or below this must be allowed to be dropped.
    guard_population(runs=MAX_RUNS + 1, observations=0, url=TEST)
    guard_population(runs=MIN_RUNS + 1, observations=0, url=TEST)

    assert MAX_FIXTURE_RUNS > MAX_RUNS, (
        "the ceiling must sit above the largest batch a test can write, or a "
        "test that writes one poisons every database test after it"
    )


def test_either_count_alone_is_enough_to_refuse() -> None:
    """A corpus whose findings were cleared still has its observations, and a
    database of runs with no observations is still not a test database."""
    # spec: ops-004
    with pytest.raises(DatabaseGuardError, match="scenario runs"):
        guard_population(runs=300, observations=0, url=TEST)
    with pytest.raises(DatabaseGuardError, match="observations"):
        guard_population(runs=0, observations=1_000_000, url=TEST)


# ------------------------------------- the guard must not be read too late


def test_the_application_url_is_captured_at_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The suite's own autouse fixture replaces `DATABASE_URL` with an
    unreachable address for every test. A guard that reads the environment
    when it *runs* therefore compares the target against a placeholder and
    waves the real database through.

    This is not a hypothetical. The first version of the guard did exactly
    that, passed every one of its unit tests, and was then pointed at the
    application's own database deliberately -- where it let eighteen tests
    drop and rebuild the schema without a word."""
    # spec: ops-004
    from tests import conftest

    captured = conftest.APPLICATION_DATABASE_URL
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x@nowhere:1/other")
    assert conftest.APPLICATION_DATABASE_URL == captured, (
        "the guard's notion of the application database changed when the "
        "environment did, which is how it comes to compare against a placeholder"
    )
