"""The Scenario Control contract, against what the generator actually is.

Spec: scn-004. The screen is built before `api-006` exists, the way the
Operational Picture was built before `api-002` did: a TypeScript contract, a
mock satisfying it, and the screen taking the value as a prop. The risk that
buys is a contract describing a generator nobody has. These tests are the price
of admission -- four shapes declared in two languages, compared in both
directions, so a field added on one side alone fails.

**What is red at the test stage and what is not.** The contract file does not
exist yet, so every parity test below fails with "not found": one cause, six
failures. That is the honest red for an item whose deliverable is the file
itself, but it means none of these assertions has yet been shown to fail *for
its own reason*. Each is mutation-proved after the implementation lands instead
-- drop one dial, rename one field -- and the results go in `docs/handoff.md`.
The exception is the first test, which asserts a property of the reader rather
than of the system and passes from the moment it is written, deliberately, and
for the reason `api-002` gives.

**`RecordedParameters` is snake_case and the rest of the contract is not.** A
run's recorded parameters are served verbatim, key for key, as the row holds
them. Re-keying them to camelCase at the boundary would mean converting back
before `RunSpec.from_record` could read them, and that function refuses a
parameter set carrying a name it does not know -- so a conversion that dropped
or renamed one field would turn a replayable run into an unreplayable one, at
the point furthest from the mistake.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.api.v1.schemas.scenario import BatchInFlight
from app.dal.models import ScenarioRunSummary
from app.pipeline import build_parser
from app.scenario.emitter import BaselineParameters, RunSpec
from app.scenario.incident import IncidentParameters, ScenarioType
from tests.contracts import (
    const_object,
    contract_paths,
    interfaces,
    read_contract,
    union_members,
)

CONTRACT_PATHS = contract_paths("scenarioControl.ts")

#: `--data-dir` says where the corpus lives, not what the run is. It is the one
#: argument the batch takes that is deployment rather than scenario, and the
#: form has no business offering it.
NOT_A_DIAL = frozenset({"data_dir"})

#: Every field a listed run may carry. A closed set rather than a list of
#: forbidden names: `api-009` is a rule about what must never appear, and the
#: only version of that rule a test can hold is one that fails on anything new.
RUN_RECORD_FIELDS = frozenset(
    {"id", "scenarioType", "seed", "startedAt", "completedAt", "parameters"}
)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _dials() -> dict[str, object]:
    """The batch entrypoint's arguments and their defaults, minus deployment."""
    namespace = build_parser().parse_args(
        ["--scenario-type", "normal-baseline", "--base-seed", "1"]
    )
    return {
        name: value for name, value in vars(namespace).items() if name not in NOT_A_DIAL
    }


def _recorded_keys() -> set[str]:
    spec = RunSpec(
        scenario_type=ScenarioType.NORMAL_BASELINE,
        parameters=BaselineParameters(),
        incident=IncidentParameters(),
        seed=1,
        start=datetime(2022, 6, 27, 12, 0, tzinfo=UTC),
        duration_seconds=900,
    )
    return set(spec.as_parameters())


def _declared() -> dict[str, dict[str, str]]:
    return interfaces(read_contract(CONTRACT_PATHS))


def test_the_contract_is_read_rather_than_skipped() -> None:
    """The guard itself, tested.

    Every parity assertion below is worthless if the file cannot be found and
    the suite quietly reports success, which is what a `skipif` would do.

    **This one passes before any implementation exists, and that is correct.**
    It asserts a property of the test harness rather than of the system, so
    there is nothing for it to fail against; it goes red if someone softens the
    reader into a skip, which is the only failure it is for.
    """
    # spec: scn-004
    with pytest.raises(AssertionError, match="not found"):
        read_contract(contract_paths("nowhere.ts"))


def test_the_parser_finds_the_contract_it_claims_to_check() -> None:
    # spec: scn-004 -- a parser that silently matched nothing would make every
    # comparison below a comparison of two empty sets, which passes
    declared = _declared()

    assert {
        "ScenarioLibraryEntry",
        "ScenarioConfiguration",
        "RecordedParameters",
        "ScenarioRunRecord",
        "ScenarioControl",
    } <= set(declared)
    assert all(fields for fields in declared.values())


def test_the_configuration_offers_every_dial_the_batch_accepts() -> None:
    """The third decision, enforced against the parser rather than a list.

    A form offering a control the generator has no input for is `scn-001`'s
    fourth failure case in a different coat: a parameter that controls nothing
    is the same defect as a seed that controls nothing. The design mockup shows
    three of them -- noise amplitude, affected sensor count, gap duration.
    """
    # spec: scn-004, scn-003, scn-001
    configuration = set(_declared()["ScenarioConfiguration"])
    dials = {_camel(name) for name in _dials()}

    assert configuration == dials


def test_the_configuration_defaults_are_the_generators_own() -> None:
    """Names matching is not enough.

    A form defaulting to values the batch would refuse sends the analyst to an
    error rather than to a run.
    """
    # spec: scn-004, scn-003
    declared = const_object(read_contract(CONTRACT_PATHS), "DEFAULT_CONFIGURATION")
    dials = _dials()

    assert declared["baseSeed"] == "null", (
        "the batch requires a base seed and the screen must not invent one: "
        "null is the request for a seed the harness chooses and records"
    )
    assert declared["scenarioType"].strip('"') in {t.value for t in ScenarioType}

    for name, value in dials.items():
        if name in {"scenario_type", "base_seed"}:
            continue
        literal = declared[_camel(name)]
        if isinstance(value, str):
            assert literal.strip('"') == value
        else:
            assert float(literal) == float(value)  # type: ignore[arg-type]


def test_the_recorded_parameters_mirror_what_a_run_row_holds() -> None:
    """Key for key, snake_case included -- see the module docstring."""
    # spec: scn-004, scn-003 -- RunSpec.from_record refuses an unknown key, so
    # a contract that renames one describes a run that cannot be replayed
    assert set(_declared()["RecordedParameters"]) == _recorded_keys()


def test_a_listed_run_carries_what_the_run_summary_carries() -> None:
    # spec: scn-004, api-006 -- plus the recorded parameters, which the summary
    # does not carry today and replay cannot do without
    declared = set(_declared()["ScenarioRunRecord"])
    summary = {_camel(name) for name in ScenarioRunSummary.model_fields}

    assert declared == summary | {"parameters"}


def test_the_contract_declares_the_five_scenario_types_and_no_sixth() -> None:
    """The closed set reaches the screen as a closed set.

    `scn-002` made spectral extent a parameter rather than a sixth type, and
    the enum has five members for that reason. A contract free to grow a sixth
    would put a type on screen that the generator cannot produce.
    """
    # spec: scn-004, scn-002, FR-202
    declared = union_members(read_contract(CONTRACT_PATHS), "ScenarioTypeId")

    assert set(declared) == {member.value for member in ScenarioType}
    assert len(declared) == 5


def test_a_listed_run_has_no_field_the_answer_key_could_travel_in() -> None:
    """`api-009`, asserted where it can still be true.

    The scenario type is on this screen legitimately -- `FR-714` requires it,
    and this screen is the evaluation harness's own face rather than the
    analyst's picture. What must never be here is what was staged: the sensors,
    the channels, the aircraft, the window. `ScenarioRunSummary` has no field
    to hold them and neither may the contract.
    """
    # spec: scn-004, api-009, scn-002
    declared = set(_declared()["ScenarioRunRecord"])

    assert declared == RUN_RECORD_FIELDS
    assert not any(
        word in field.lower()
        for field in declared
        for word in ("truth", "answer", "injected", "aircraft", "sensors", "channels")
    )


# ------------------------------------------------------- a batch already running


def test_the_in_flight_batch_is_declared_as_the_backend_reports_it() -> None:
    """The 409 body, field for field. Spec: api-011 (fourth finding).

    The refusal carries facts rather than prose precisely so it can be asserted
    field by field, and this is where that pays: the screen composes its sentence
    out of these names, so a rename on either side leaves the analyst reading
    `undefined` about a batch that really is running -- visible only by starting
    two batches by hand.
    """
    # spec: api-011, api-006
    declared = set(_declared()["InFlightBatch"])
    served = {_camel(name) for name in BatchInFlight.model_fields}

    assert declared == served


def test_the_in_flight_batch_carries_no_field_the_answer_key_could_travel_in() -> None:
    """`api-009` at the one response added since it was written.

    The scenario type is legitimate here for `FR-714`'s reason -- the analyst
    chose it, and this screen is the harness's own face. What was *staged* is
    not: no window, no sensors, no aircraft, no incident.
    """
    # spec: api-011, api-009
    declared = set(_declared()["InFlightBatch"])

    assert declared == {"scenarioType", "baseSeed", "startedAt"}
