"""The hosted arm: what is sent, what is asked, and what comes back. Spec: ai-004.

The first thing in this project that spends money, and the first that asks
a model to turn evidence into an account a person can act on. Four pieces,
and each of them is a place a guarantee can quietly die.

**What leaves the machine is a module, not a measurement script.** Section
4 of the phase 9 document measured the egress payload field by field, and
that measurement is what closed the data-egress gate and what NFR-405 rests
on. It was taken against a dict hand-written inside a measurement script,
and nothing in `app/` serialised a bundle at all -- so the thing measured
was not the thing that would be sent. The serialiser lives here now, and
the suite holds it to the bundle's own field list, so a field added
upstream cannot be silently dropped from what a model sees.

**The prompt is the experiment's largest variable.** Two arms given
different instructions are not two answers to one question, so it is
written once, reviewed, and pinned by fingerprint into every row. Drift
mid-campaign is invisible in the output; a SHA-256 makes it detectable.

**A constrained schema does not carry every guarantee.** Strict mode
honours structure -- fields, types, the three-value confidence enum,
`additionalProperties: false` -- and not quantity. `minLength` and
`minItems` do not survive, so an empty supporting-evidence list is
conformant to the provider and invalid to us. Those guarantees **move** to
parse time: still enforced, as a refusal rather than an impossibility. That
corrects this project's reading of §10, which held that a validation
failure from this arm must mean the provider broke its own constraint.

**No test makes a real call.** The client is injected, and the adapter is
proved not to build one when it is given one.

**Twelve of these pass against do-nothing stubs, and are named rather than
pretended away**: the exclusion-set pin, the estimate docstring and the
registry construction assert *declarations*; the fingerprint derivation and
its sensitivity to an edit are properties of SHA-256 that any honest
implementation has; the three schema-shape assertions and the no-mutation
check are satisfied by a narrower that does nothing, which is correct --
they exist to catch one that *widens*, which is `ai-001`'s warning; the
parse-time enforcement is a property of `ai-001` recorded here as a
dependency; the same-bytes check is a purity property; and the
dated-model-id acceptance is the positive half of a pair whose refusing
half is red.
Seven others passed for a reason other than their name and were rewritten:
four were negative or determinism assertions satisfied by a near-empty
payload, one checked a key existed rather than its contents, and one was
satisfied by a narrower that dropped nothing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from types import SimpleNamespace

import pytest

from app.ai.hypothesis import Hypothesis, hypothesis_json_schema
from app.ai.payload import BUNDLE_EXCLUDED, ITEM_EXCLUDED, bundle_payload, payload_json
from app.ai.prompt import HYPOTHESIS_PROMPT, prompt_fingerprint
from app.ai.providers.openai import (
    UNSUPPORTED_BY_STRICT_MODE,
    OpenAIGenerator,
    strict_schema,
)
from app.ai.registry import PROVIDERS, build_generator
from app.ai.service import (
    ConfigurationError,
    GenerationConfig,
    GenerationRefused,
    GeneratorKind,
    ProviderUnavailable,
)
from app.ai.template import generate as template_generate
from app.detection.bundle import EvidenceBundle, EvidenceItem, SupersededClaim
from tests.test_ai_template import fault_bundle, zone_bundle

DATED_MODEL = "gpt-4o-2024-08-06"


def hosted_config(**kw) -> GenerationConfig:
    kw.setdefault("provider", "openai")
    kw.setdefault("model_id", DATED_MODEL)
    kw.setdefault("parameters", {"temperature": 0.0, "max_tokens": 2000})
    return GenerationConfig(**kw)


def a_valid_response(bundle: EvidenceBundle | None = None) -> str:
    """A response the schema accepts, built from the mechanical generator.

    Using `ai-002`'s output as the model's stand-in is deliberate: it is
    the one input whose correct answer is known in advance.
    """
    return template_generate(bundle or fault_bundle()).model_dump_json()


class _FakeCompletions:
    """Stands in for `client.chat.completions`. Never reaches a network."""

    def __init__(self, *, content=None, refusal=None, raises=None, usage=None):
        self.content = content
        self.refusal = refusal
        self.raises = raises
        self.usage = usage or SimpleNamespace(prompt_tokens=1200, completion_tokens=400)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.raises is not None:
            raise self.raises
        message = SimpleNamespace(content=self.content, refusal=self.refusal)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=self.usage,
        )


def fake_client(**kw) -> SimpleNamespace:
    completions = _FakeCompletions(**kw)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def an_arm(client=None, config=None, **kw) -> OpenAIGenerator:
    return OpenAIGenerator(
        config or hosted_config(),
        client=client
        if client is not None
        else fake_client(content=a_valid_response()),
        **kw,
    )


# ------------------------------------------- what leaves the machine, as a module


def test_the_payload_carries_every_bundle_field_but_the_named_exclusions():
    # spec: ai-004, NFR-405 -- THE test this module exists for. The egress
    # measurement that closed the data-egress gate was taken against a dict
    # written inside a measurement script; a field added to a bundle after
    # it would be silently absent from what a model sees, and the figure of
    # record would describe something that is no longer sent.
    payload = bundle_payload(fault_bundle())
    fields = {f.name for f in dataclasses.fields(EvidenceBundle)}

    assert set(payload) == fields - BUNDLE_EXCLUDED


def test_an_evidence_item_carries_every_field_but_the_named_exclusions():
    # spec: ai-004 -- the same rule one level down, where the citations a
    # model must resolve against actually live.
    payload = bundle_payload(fault_bundle())
    fields = {f.name for f in dataclasses.fields(EvidenceItem)}

    assert set(payload["evidence"][0]) == fields - ITEM_EXCLUDED


def test_the_exclusions_are_exactly_the_two_that_were_argued_for():
    # spec: ai-004 -- an exclusion set that can quietly grow is the same
    # defect the payload module exists to fix, one level up. Both of these
    # are OUR bookkeeping rather than evidence: a database key for the run,
    # and the row ids evb-002 resolved the citations to. Neither is usable
    # by a model, which cannot query the store, and both were absent from
    # the payload section 4 measured -- so pinning them here is also what
    # keeps the shipped serialiser and the figure of record describing the
    # same thing. A third exclusion has to be argued for in this test.
    assert BUNDLE_EXCLUDED == frozenset({"scenario_run_id"})
    assert ITEM_EXCLUDED == frozenset({"observation_ids"})


def test_no_database_identifier_reaches_the_provider():
    # spec: ai-004, NFR-405 -- the exclusions stated as a property of the
    # bytes rather than of the key set, so a nested copy would be caught
    # too.
    serialised = payload_json(fault_bundle())

    assert len(serialised) > 1000
    assert "scenario_run_id" not in serialised
    assert "observation_ids" not in serialised


def test_the_frequency_axis_reaches_the_payload():
    # spec: ai-004, evb-001 -- the channel list is the bundle's OWN
    # contribution: anom-001 raises episodes per sensor per channel and
    # nothing upstream merges them. Dropped here it is the one axis of the
    # claim a model never sees, and nothing else in the payload replaces it.
    payload = bundle_payload(zone_bundle())

    assert payload["affected_channels"] == list(zone_bundle().affected_channels)
    assert payload["affected_channels"]


def test_the_payload_is_json_serialisable_without_a_custom_encoder():
    # spec: ai-004 -- datetimes and enums have to be converted here rather
    # than by whatever happens to serialise them later, or two callers
    # produce two different payloads from one bundle.
    payload = bundle_payload(zone_bundle())

    # Round-tripped rather than merely dumped: a stub payload carrying
    # almost nothing is trivially serialisable, and this has to fail on one.
    assert json.loads(json.dumps(payload)) == payload
    assert isinstance(payload["time_window"][0], str)
    # `type(...) is str`, not isinstance: these enums subclass str, so an
    # enum member left in the payload passes an isinstance check, compares
    # equal to its value, and json.dumps serialises it identically. The
    # module claims every value is already a JSON primitive, and only the
    # exact type holds that claim.
    assert type(payload["evidence"][0]["data_mode"]) is str
    assert type(payload["evidence"][0]["grounding"]) is str


def test_the_same_bundle_always_produces_the_same_bytes():
    # spec: ai-004, NFR-601 -- the campaign compares arms on the same input,
    # so "the same bundle" has to mean the same bytes and not merely the
    # same object.
    assert payload_json(fault_bundle()) == payload_json(fault_bundle())
    # And DIFFERENT bundles must not: without this the test cannot tell a
    # pure function from a constant, and a stub returning the same string
    # for everything satisfies the line above.
    assert payload_json(fault_bundle()) != payload_json(zone_bundle())


def test_rejected_claims_are_sent_rather_than_hidden():
    # spec: ai-004, ai-008, evb-001 -- a suppressed claim is a competing
    # conclusion. Sending it is what lets a model write an honest
    # alternative, and it creates exactly the trap ai-008 exists to catch: a
    # hypothesis citing a rejected claim as SUPPORT.
    #
    # A bundle is CONSTRUCTED with one, because the corpus produces none --
    # ladder_suppression.py records 188 claims bid and 0 suppressed -- so a
    # test over a real bundle would assert an empty list is present and pass
    # with the contents dropped.
    rejected = SupersededClaim(
        rule_id="SENSOR-FAULT",
        anomaly_type="possible_sensor_fault",
        claimed_by="FUSION-SPATIAL",
        reason="a higher rule had already claimed this zone",
    )
    bundle = dataclasses.replace(fault_bundle(), superseded=(rejected,))

    payload = bundle_payload(bundle)
    assert payload["superseded"][0]["rule_id"] == "SENSOR-FAULT"
    assert payload["superseded"][0]["claimed_by"] == "FUSION-SPATIAL"


def test_the_payload_names_no_scenario_type():
    # spec: ai-004, api-009 -- the AI must never learn which scenario it is
    # looking at, or the comparison measures recall of the taxonomy rather
    # than reasoning over evidence.
    serialised = payload_json(fault_bundle()) + payload_json(zone_bundle())

    # A negative assertion is satisfied by an empty haystack, so the
    # haystack is pinned as substantial first.
    assert len(serialised) > 2000
    for scenario in (
        "gnss-degradation",
        "rf-sensor-fault",
        "aircraft-coverage-gap",
        "ambiguous-mixed-evidence",
        "normal-baseline",
    ):
        assert scenario not in serialised


# --------------------------------------------------- the prompt, pinned


def test_the_fingerprint_is_the_prompt():
    # spec: ai-004 -- a fingerprint that is not derived from the text is a
    # constant, and a constant records nothing.
    expected = hashlib.sha256(HYPOTHESIS_PROMPT.encode("utf-8")).hexdigest()

    assert prompt_fingerprint() == expected


def test_editing_the_prompt_moves_the_fingerprint():
    # spec: ai-004 -- the whole point. Drift mid-campaign is invisible in
    # the output and has to be visible in the row.
    edited = HYPOTHESIS_PROMPT + " "
    assert hashlib.sha256(edited.encode("utf-8")).hexdigest() != prompt_fingerprint()


def test_the_prompt_states_the_rules_it_must_state():
    # spec: ai-004, ai-001, ai-008 -- each of these corresponds to a
    # guarantee elsewhere that the model is the only one able to honour.
    # Losing one during an edit would be invisible until the campaign.
    # Each is a phrase the rule cannot lose and still mean what it means.
    # A mutation pass caught the first version of this test matching words
    # that survive the rule being gutted: "superseded" is still there when
    # rule 3 becomes "the superseded list holds earlier notes", and
    # "rule_id and finding_type" is still there when the citation rule stops
    # requiring them to be copied from the package.
    for required in (
        "Low, Medium or High",
        "never a number",
        "REJECTED",
        "never cite one as supporting evidence",
        "copied exactly",
        "at least one genuine entry",
        "pseudonyms",
        "rule_id and finding_type",
    ):
        assert required in HYPOTHESIS_PROMPT


def test_the_prompt_names_no_scenario_type():
    # spec: ai-004, api-009 -- the same rule as the payload, at the other
    # end of the request.
    assert len(HYPOTHESIS_PROMPT) > 800
    for scenario in ("gnss-degradation", "rf-sensor-fault", "normal-baseline"):
        assert scenario not in HYPOTHESIS_PROMPT


# ---------------------------------- a constrained schema, and what it cannot carry


def test_the_confidence_enum_survives_narrowing():
    # spec: ai-004, ai-001, FR-715 -- the guarantee that MUST NOT move.
    # ai-001 warns that a derivation widening confidence to a free string
    # would pass every test written against the Python model and lose the
    # restriction at the only boundary relying on it.
    schema, _ = strict_schema()

    assert schema["$defs"]["Confidence"]["enum"] == ["Low", "Medium", "High"]


def test_every_object_forbids_extra_properties_after_narrowing():
    # spec: ai-004 -- strict mode requires it, and it is also what stops a
    # model inventing a field an analyst would read as system output.
    schema, _ = strict_schema()

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Citation"]["additionalProperties"] is False


def test_every_property_stays_required_after_narrowing():
    # spec: ai-004, ai-001 -- nothing defaults, so a field a generator
    # omitted must not arrive looking like a field it considered and left
    # empty.
    schema, _ = strict_schema()

    assert set(schema["required"]) == set(schema["properties"])


def test_the_quantitative_constraints_do_not_survive():
    # spec: ai-004 -- and this is the finding rather than a detail. Strict
    # mode does not honour minLength or minItems, so they are dropped
    # rather than sent and silently ignored.
    schema, dropped = strict_schema()

    assert "minItems" not in json.dumps(schema)
    assert "minLength" not in json.dumps(schema)
    assert "minItems" in dropped and "minLength" in dropped


def test_what_was_dropped_is_reported_rather_than_discarded():
    # spec: ai-004 -- a narrowing that does not say what it removed is a
    # place for a guarantee to vanish between versions of a provider's API.
    _, dropped = strict_schema()

    # Non-empty first: an empty tuple is a subset of anything and is
    # already sorted, so both lines below pass on a narrower that removed
    # nothing at all.
    assert dropped
    assert set(dropped) <= UNSUPPORTED_BY_STRICT_MODE
    assert dropped == tuple(sorted(dropped))


def test_the_dropped_guarantees_are_still_enforced_at_parse_time():
    # spec: ai-004, ai-001, ai-007 -- they MOVED, they were not lost. An
    # empty supporting-evidence list is conformant to the provider and
    # invalid to us, so it arrives as a refusal rather than as an
    # impossibility -- which is why a malformed refusal from this arm is not
    # automatically the alarming event section 10 described.
    good = json.loads(a_valid_response())
    good["supporting_evidence"] = []

    with pytest.raises(Exception):
        Hypothesis.model_validate(good)


def test_narrowing_does_not_mutate_the_shared_schema():
    # spec: ai-004, ai-001 -- ai-001 deep-copies for exactly this reason,
    # and a narrower that edited in place would undo it for every later
    # caller.
    before = json.dumps(hypothesis_json_schema(), sort_keys=True)
    strict_schema()

    assert json.dumps(hypothesis_json_schema(), sort_keys=True) == before


# ------------------------------------------------ the model id, pinned and dated


def test_a_moving_alias_is_refused():
    # spec: ai-004 -- the item's named failure case. An alias changing
    # mid-campaign invalidates the comparison with NO visible error, which
    # is the worst available failure mode.
    with pytest.raises(ConfigurationError) as raised:
        an_arm(config=hosted_config(model_id="gpt-4o"))

    assert "dated" in str(raised.value).lower()


def test_a_dated_model_id_is_accepted():
    # spec: ai-004 -- and the guard has to let the real thing through, or
    # it is a guard somebody switches off.
    assert an_arm(config=hosted_config(model_id=DATED_MODEL)).model_id == DATED_MODEL


def test_an_arm_with_no_model_id_at_all_is_refused():
    # spec: ai-004, ai-003 -- None means "this provider has no model", which
    # is true of the template and false here.
    with pytest.raises(ConfigurationError):
        an_arm(config=hosted_config(model_id=None))


def test_the_provider_is_registered_under_its_own_name():
    # spec: ai-004, ai-003 -- one adapter module and one line, which is the
    # extensibility claim this item is the second data point for.
    assert "openai" in PROVIDERS


def test_the_registry_builds_this_arm():
    # spec: ai-004, ai-003 -- driven through the port, so nothing outside
    # can tell which arm it holds.
    built = build_generator(
        hosted_config(), providers={"openai": lambda c: an_arm(config=c)}
    )

    assert isinstance(built, OpenAIGenerator)


# ------------------------------------------- the request, and what it carries


def test_the_request_is_constrained_by_the_narrowed_schema():
    # spec: ai-004, FR-504 -- schema conformance as a generation-time
    # guarantee is the whole reason this arm is built the way it is.
    client = fake_client(content=a_valid_response())
    an_arm(client).generate(fault_bundle())

    sent = client.chat.completions.requests[0]
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    # And the NARROWED one. Sending the schema unnarrowed is rejected by the
    # live API, so every call in the campaign would fail -- and nothing here
    # would have noticed, because the envelope is identical either way.
    sent_schema = json.dumps(sent["response_format"]["json_schema"]["schema"])
    assert "minItems" not in sent_schema
    assert "minLength" not in sent_schema
    assert '"Low"' in sent_schema


def test_the_request_carries_the_prompt_and_the_payload():
    # spec: ai-004 -- and the bundle goes in as the serialised payload
    # rather than as prose, so what a model reads is the thing that was
    # measured.
    client = fake_client(content=a_valid_response())
    an_arm(client).generate(fault_bundle())

    messages = client.chat.completions.requests[0]["messages"]
    assert any(HYPOTHESIS_PROMPT in m["content"] for m in messages)
    assert any(payload_json(fault_bundle()) in m["content"] for m in messages)


def test_the_frozen_parameters_reach_the_request():
    # spec: ai-004, ai-003 -- a campaign whose arms ran under different
    # parameters is not a comparison, and the parameters are supplied once
    # at construction for exactly that reason.
    client = fake_client(content=a_valid_response())
    an_arm(client).generate(fault_bundle())

    assert client.chat.completions.requests[0]["temperature"] == 0.0


def test_no_client_is_built_when_one_is_supplied(monkeypatch):
    # spec: ai-004 -- "tests mock the provider and never make a real call"
    # is a constraint on the adapter, not an instruction to test authors. An
    # adapter that built a client anyway would need a key to be tested at
    # all, and would eventually be tested against the real thing.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    an_arm().generate(fault_bundle())


def test_a_missing_credential_fails_loudly_rather_than_unauthenticated(monkeypatch):
    # spec: ai-004 -- following PSEUDONYM_SEED: no default, and a loud
    # failure rather than a silent fallback.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError) as raised:
        OpenAIGenerator(hosted_config(), client=None)

    assert "OPENAI_API_KEY" in str(raised.value)


# -------------------------------------------- what comes back, and its provenance


def test_a_good_answer_becomes_a_hosted_result():
    # spec: ai-004, ai-003
    result = an_arm().generate(fault_bundle())

    assert result.generator is GeneratorKind.HOSTED
    assert result.call is not None
    assert result.call.model_id == DATED_MODEL


def test_the_verbatim_response_is_stored_rather_than_re_serialised():
    # spec: ai-004, db-002, NFR-602 -- a response reconstructed from the
    # parsed hypothesis is a record of what we understood, not of what was
    # said, and it is the only thing that makes a grounding failure
    # investigable after the fact.
    raw = a_valid_response()
    result = an_arm(fake_client(content=raw)).generate(fault_bundle())

    assert result.call is not None
    assert result.call.raw_response == raw


def test_the_prompt_fingerprint_is_recorded_on_every_call():
    # spec: ai-004 -- the second named failure case. Nothing else in the row
    # records which instructions ran, and two days given different
    # instructions are not one comparison.
    result = an_arm().generate(fault_bundle())

    assert result.call is not None
    assert result.call.parameters["prompt_sha256"] == prompt_fingerprint()


def test_the_configured_parameters_are_recorded_beside_it():
    # spec: ai-004, db-002 -- the reproducibility claim is the parameters
    # AND the instructions, not one of them.
    result = an_arm().generate(fault_bundle())

    assert result.call is not None
    assert result.call.parameters["temperature"] == 0.0


def test_a_config_faking_its_own_fingerprint_is_refused():
    # spec: ai-004 -- the fingerprint is evidence about which instructions
    # ran. A caller supplying one is writing that evidence by hand.
    with pytest.raises(ConfigurationError):
        an_arm(config=hosted_config(parameters={"prompt_sha256": "deadbeef"}))


def test_token_usage_is_recorded_from_the_first_call():
    # spec: ai-004, ai-009, FR-514 -- retrofitting loses the
    # development-phase spend data that makes the campaign estimate
    # credible.
    result = an_arm().generate(fault_bundle())

    assert result.call is not None
    assert result.call.usage.prompt_tokens == 1200
    assert result.call.usage.completion_tokens == 400


def test_cost_is_absent_when_no_prices_are_supplied():
    # spec: ai-004, ai-009 -- the provider returns token counts, not money.
    # An absent cost is honest; a zero would claim the call was free.
    result = an_arm().generate(fault_bundle())

    assert result.call is not None
    assert result.call.usage.cost_usd is None


def test_cost_is_computed_when_prices_are_supplied():
    # spec: ai-004, ai-009 -- and this is what makes ai-009's spend ceiling
    # anything other than inert on this arm, which it otherwise is.
    result = an_arm(
        usd_per_1k_prompt=0.0025, usd_per_1k_completion=0.01
    ).generate(fault_bundle())

    assert result.call is not None
    expected = 1200 / 1000 * 0.0025 + 400 / 1000 * 0.01
    assert result.call.usage.cost_usd == pytest.approx(expected)


def test_prices_are_not_recorded_as_generation_parameters():
    # spec: ai-004, ai-003 -- a price is a fact about billing, not about
    # what the model did, and generation_params is read back as the
    # reproducibility record.
    result = an_arm(usd_per_1k_prompt=0.0025, usd_per_1k_completion=0.01).generate(
        fault_bundle()
    )

    assert result.call is not None
    assert not [k for k in result.call.parameters if "usd" in k or "price" in k]


def test_a_computed_cost_is_documented_as_an_estimate():
    # spec: ai-004, ai-009 -- the provider console is the authority, and a
    # figure quoted from here is derived from a price we typed in.
    assert "estimate" in inspect.getdoc(OpenAIGenerator.__init__).lower()


# ------------------------------------------ failure, sorted into the right box


@pytest.mark.parametrize(
    "error_name",
    [
        "APIConnectionError",
        "APITimeoutError",
        "AuthenticationError",
        "PermissionDeniedError",
        "RateLimitError",
        "InternalServerError",
    ],
)
def test_the_provider_being_unusable_is_an_availability_failure(error_name):
    # spec: ai-004, ai-006 -- nothing was wrong with the request, so the
    # answer is to ask the same question somewhere else. ai-007 must not
    # see these.
    import openai

    error = _an_openai_error(getattr(openai, error_name))

    with pytest.raises(ProviderUnavailable):
        an_arm(fake_client(raises=error)).generate(fault_bundle())


def test_a_rejected_request_is_a_misconfiguration_and_not_a_refusal():
    # spec: ai-004, ai-003 -- a 400 means WE sent something wrong, most
    # likely a schema the API will not take. Retried or fallen back from, it
    # would run the whole campaign on template output while the run
    # reported itself as hosted.
    import openai

    with pytest.raises(ConfigurationError):
        an_arm(fake_client(raises=_an_openai_error(openai.BadRequestError))).generate(
            fault_bundle()
        )


def test_a_model_that_declines_to_answer_is_a_correctness_refusal():
    # spec: ai-004, ai-007 -- the request reached a model and the model's
    # answer was the problem, so the response is to retry here and then fall
    # back, never to ask a different model the same question.
    client = fake_client(content=None, refusal="I cannot help with that.")

    with pytest.raises(GenerationRefused) as raised:
        an_arm(client).generate(fault_bundle())

    # Which refusal, not merely that one happened: with the declining branch
    # removed the empty-content guard raises GenerationRefused too, so a
    # bare `pytest.raises` passes on an implementation that ignores a model
    # declining to answer entirely.
    assert "declined" in str(raised.value)


def test_an_unparseable_answer_is_refused_as_structural():
    # spec: ai-004, ai-007 -- this one IS the alarming event: constrained
    # decoding makes it impossible in the ordinary course, so it means the
    # provider broke its own guarantee.
    with pytest.raises(GenerationRefused) as raised:
        an_arm(fake_client(content="{not json")).generate(fault_bundle())

    assert "structur" in str(raised.value).lower()


def test_a_constraint_the_schema_could_not_express_is_refused_as_such():
    # spec: ai-004, ai-007 -- and this one is ORDINARY, which corrects the
    # reading recorded on ai-007. minItems does not survive narrowing, so an
    # empty supporting-evidence list is conformant to the provider and
    # invalid here. Folding it in with the structural failures would bury
    # the alarming event under the expected one.
    body = json.loads(a_valid_response())
    body["supporting_evidence"] = []

    with pytest.raises(GenerationRefused) as raised:
        an_arm(fake_client(content=json.dumps(body))).generate(fault_bundle())

    assert "structur" not in str(raised.value).lower()


def test_a_confidence_outside_the_three_is_refused_as_structural():
    # spec: ai-004, ai-001, FR-715 -- the enum DOES survive narrowing, so a
    # value outside it means the provider did not honour the schema it was
    # given. That makes this the alarming kind of refusal rather than the
    # ordinary one, and it is the guarantee ai-001 says must not be lost at
    # this boundary.
    body = json.loads(a_valid_response())
    body["confidence"] = "Certain"

    with pytest.raises(GenerationRefused) as raised:
        an_arm(fake_client(content=json.dumps(body))).generate(fault_bundle())

    assert "structur" in str(raised.value).lower()


def test_the_environment_path_builds_a_real_client(monkeypatch):
    # spec: ai-004 -- every other test injects a client, so nothing
    # exercised the branch that actually authenticates. Constructing the
    # client makes no request, so this stays offline.
    import openai

    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")

    arm = OpenAIGenerator(hosted_config())

    assert isinstance(arm.client, openai.OpenAI)


def test_a_blank_credential_is_treated_as_missing(monkeypatch):
    # spec: ai-004 -- an empty string satisfies "the variable is set" while
    # naming nothing, which is the same defect ai-003's ModelCall refuses.
    monkeypatch.setenv("OPENAI_API_KEY", "   ")

    with pytest.raises(ConfigurationError):
        OpenAIGenerator(hosted_config())


def test_a_refused_call_still_carries_what_it_paid_for():
    # spec: ai-004, ai-009 -- tokens were spent on an answer nobody can use,
    # and those are the calls a retry loop is made of.
    with pytest.raises(GenerationRefused) as raised:
        an_arm(fake_client(content="{not json")).generate(fault_bundle())

    assert raised.value.call is not None
    assert raised.value.call.raw_response == "{not json"


def test_an_empty_answer_is_refused_rather_than_stored():
    # spec: ai-004, ai-003 -- ModelCall refuses a blank raw_response, and
    # the adapter must not be the thing that discovers it.
    with pytest.raises(GenerationRefused) as raised:
        an_arm(fake_client(content="")).generate(fault_bundle())

    # Again, which one: without this guard the empty string reaches
    # json.loads and is refused as malformed JSON, so the test passes while
    # the specific check it names has been deleted.
    assert "empty" in str(raised.value)


def _an_openai_error(cls):
    """Build one of the SDK's errors without a live request object.

    `httpx2`, not `httpx`: openai 3.x carries its own fork, and importing
    the wrong one fails at collection rather than at assertion -- which is
    how it was found.
    """
    import httpx2
    import openai

    request = httpx2.Request("POST", "https://example.invalid/v1/chat/completions")
    if issubclass(cls, openai.APIStatusError):
        status = {
            openai.AuthenticationError: 401,
            openai.PermissionDeniedError: 403,
            openai.RateLimitError: 429,
            openai.BadRequestError: 400,
            openai.InternalServerError: 500,
        }[cls]
        response = httpx2.Response(status, request=request)
        return cls("boom", response=response, body=None)
    if cls is openai.APITimeoutError:
        return cls(request=request)
    return cls(message="boom", request=request)
