"""Drawing the twenty packages the campaign will be asked about. Spec: eval-004.

The first of this item's **two passes**, and they run at different times. This
one happens *before* any scored request is made and is committed; the export
of rendered pairs happens after the campaign. Nothing in the backlog owned
producing the sample until the amendment gave it here, which is the kind of
gap that only appears when something finally needs it.

**Why the order of the draw matters more than the draw.** The whole force of
"the instrument provably predates the results" collapses if the *corpus* does
not. A sample chosen after seeing how the first few packages turned out is a
sample chosen to produce an answer, and no amount of pre-registering the
rubric repairs that. So the draw is reproducible from one number, the
population it drew from is recorded beside it, and `ai-012` refuses to invent
a sample of its own.

**Stratified on bundle kind, and the strata are a constant rather than an
argument.** Five scenario types produce two kinds of bundle; one anomalous
type produces none at all, which is why the plan's "five from each of four
types" describes a corpus that cannot exist. Making the strata configurable
would let the pre-registered stratification be changed silently, so they are
fixed here and a bundle of an unrecognised kind is **refused rather than
ignored** -- an unknown kind means a third rule has started producing
bundles, and the stratification needs revisiting rather than quietly
outliving the corpus it was written for.

**The scenario type goes beside the sample and never inside a bundle.** It is
ground truth: `api-009` keeps it out of what the detection engine sees and
`evb-001` keeps it out of what the model sees. The author's own record of
which sample came from where is a different object with a different audience,
and it is needed because the two fault-producing scenario types have to be
comparable afterwards without having been stratified on.

These tests touch no database. The sampler is a pure function over bundles
already read, which is what lets the corpus decision be checked without
Docker and without a corpus.
"""

from __future__ import annotations

import json
import random
from dataclasses import replace

import pytest

from app.ai.service import ConfigurationError
from app.detection.fusion import ANOMALY_TYPE as INTERFERENCE
from app.detection.sensor_fault import ANOMALY_TYPE as FAULT
from app.evaluation.sampling import PER_KIND, STRATA, BundleSample, draw_sample
from tests.test_ai_template import fault_bundle, zone_bundle

SEED = 20260927


# ------------------------------------------------------------------ the corpus


def corpus(interference: int = 20, fault: int = 21):
    """A stand-in for the stored bundles: distinct ids, two kinds, one per run.

    Shaped like the real thing -- 41 bundles, 20 of one kind and 21 of the
    other -- because the sample has to be drawable from what actually exists
    and 10 of each is comfortable on one and tight on neither.
    """
    made = []
    for n in range(interference):
        made.append((100 + n, replace(zone_bundle(tracks=False), scenario_run_id=n)))
    for n in range(fault):
        made.append((200 + n, replace(fault_bundle(), scenario_run_id=1000 + n)))
    return made


def scenario_types(available, interference="gnss-degradation", fault="rf-sensor-fault"):
    return {
        bundle.scenario_run_id: (
            interference if bundle.anomaly_type == INTERFERENCE else fault
        )
        for _, bundle in available
    }


def drawn(available=None, **kw) -> BundleSample:
    available = corpus() if available is None else available
    kw.setdefault("scenario_types", scenario_types(available))
    kw.setdefault("seed", SEED)
    return draw_sample(available, **kw)


# --------------------------------------------------------------- what it draws


def test_it_draws_ten_of_each_kind() -> None:
    # spec: eval-004 -- 10 interference and 10 fault, keeping the planned 20
    # bundles and 40 hypotheses. Balancing by kind also gives a scorer
    # roughly equal numbers of long and short documents, where the original
    # stratification would have given three-quarters short ones.
    sample = drawn()

    by_kind: dict[str, int] = {}
    for entry in sample.entries:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1

    assert by_kind == {INTERFERENCE: PER_KIND, FAULT: PER_KIND}
    assert len(sample.entries) == 2 * PER_KIND
    assert PER_KIND == 10


def test_the_strata_are_the_two_kinds_the_corpus_really_produces() -> None:
    # spec: eval-004 -- read off the constants the rules themselves declare
    # rather than spelled here, because two spellings of one vocabulary
    # eventually differ by a letter and the sample silently loses a stratum.
    assert set(STRATA) == {INTERFERENCE, FAULT}


def test_the_same_number_draws_the_same_twenty() -> None:
    # spec: eval-004, NFR-601 -- a sample nobody can redraw is a sample
    # nobody can check.
    assert [e.bundle_id for e in drawn().entries] == [
        e.bundle_id for e in drawn().entries
    ]


def test_a_different_number_draws_a_different_twenty() -> None:
    # spec: eval-004 -- the seed has to matter, or "seeded" is decoration
    # and the draw is whatever order the store happened to return.
    assert [e.bundle_id for e in drawn().entries] != [
        e.bundle_id for e in drawn(seed=SEED + 1).entries
    ]


def test_the_draw_does_not_depend_on_the_order_it_was_handed() -> None:
    # spec: eval-004, db-009 -- the failure this repository has recorded
    # three times. The store returns rows in whatever order it finds them,
    # and a draw seeded consistently but fed an inconsistent population is
    # reproducible only by accident.
    available = corpus()
    shuffled = list(available)
    random.Random(7).shuffle(shuffled)
    assert [bundle_id for bundle_id, _ in shuffled] != [
        bundle_id for bundle_id, _ in available
    ], "the fixture has to actually be shuffled for this to test anything"

    assert [e.bundle_id for e in drawn(available).entries] == [
        e.bundle_id for e in drawn(shuffled).entries
    ]


def test_the_entries_come_back_in_a_fixed_order() -> None:
    # spec: eval-004 -- the sample is a set, and its order is not a variable
    # this experiment should introduce. The order a *scorer* sees is
    # randomised separately by the export, which is the order blinding
    # depends on.
    ids = [e.bundle_id for e in drawn().entries]

    assert ids == sorted(ids)


# --------------------------------------------- ground truth, kept to one side


def test_every_entry_records_the_scenario_type_that_produced_it() -> None:
    # spec: eval-004 -- so the two fault-producing scenario types can be
    # compared afterwards without having been stratified on.
    sample = drawn()

    for entry in sample.entries:
        expected = (
            "gnss-degradation" if entry.kind == INTERFERENCE else "rf-sensor-fault"
        )
        assert entry.scenario_type == expected


def test_the_bundle_itself_never_learns_the_scenario_type() -> None:
    # spec: eval-004, api-009, evb-001 -- the scenario type is ground truth.
    # The bundle is what the model sees; the sample record is what the author
    # keeps, and they have different audiences.
    sample = drawn()

    for entry in sample.entries:
        assert not hasattr(entry.bundle, "scenario_type")
        assert "gnss-degradation" not in str(entry.bundle)


def test_the_sample_is_handed_over_in_the_shape_the_campaign_takes() -> None:
    # spec: eval-004, ai-012 -- the campaign refuses to invent a sample, so
    # what it is given has to arrive in the shape its reader already returns,
    # with nothing in between to get wrong.
    sample = drawn()

    handed = sample.for_campaign

    assert handed == tuple((e.bundle_id, e.bundle) for e in sample.entries)
    assert all(isinstance(bundle_id, int) for bundle_id, _ in handed)


# ---------------------------------------------------- what it refuses to draw


def test_a_kind_with_too_few_bundles_is_refused() -> None:
    # spec: eval-004 -- drawing nine where ten were pre-registered is a
    # corpus quietly smaller than the one the instrument was written for,
    # and it would be discovered, if at all, when the counts were reported.
    with pytest.raises(ConfigurationError, match="9 of"):
        drawn(corpus(interference=9))


def test_a_bundle_of_an_unknown_kind_is_refused_rather_than_ignored() -> None:
    # spec: eval-004, anom-013 -- ignoring it would keep a stratification
    # the corpus has outgrown, silently. A third kind means a third rule has
    # started producing bundles and the pre-registration needs revisiting.
    available = corpus()
    available.append((999, replace(fault_bundle(), anomaly_type="possible_something")))

    with pytest.raises(ConfigurationError, match="possible_something"):
        drawn(available)


def test_a_repeated_bundle_is_refused() -> None:
    # spec: eval-004, ai-012 -- the same bundle twice is counted twice in
    # every per-arm figure while looking like two bundles.
    available = corpus()
    available.append(available[0])

    with pytest.raises(ConfigurationError, match="more than once"):
        drawn(available)


def test_a_bundle_whose_run_has_no_scenario_type_is_refused() -> None:
    # spec: eval-004 -- an entry recording no scenario type is one the
    # afterwards-comparison cannot use, and a sample that is 19 usable
    # entries and one blank is worse than one that refused to be drawn.
    available = corpus()
    types = scenario_types(available)
    del types[available[0][1].scenario_run_id]

    with pytest.raises(ConfigurationError, match="no scenario type"):
        drawn(available, scenario_types=types)


def test_fewer_than_one_per_kind_is_refused() -> None:
    # spec: eval-004 -- a sample of nothing is drawable, reproducible, and
    # not a corpus.
    with pytest.raises(ConfigurationError, match="per kind"):
        drawn(per_kind=0)


# ------------------------------------------------------------- the artefact


def test_the_record_names_the_population_it_drew_from() -> None:
    # spec: eval-004 -- stronger than a sentence describing the rule, which
    # is a second copy of the code and drifts from it. Recording the seed
    # and the exact ordered population lets a reader re-run the draw rather
    # than take its word.
    available = corpus()

    sample = drawn(available)

    assert sample.seed == SEED
    assert sample.per_kind == PER_KIND
    assert sample.population[INTERFERENCE] == tuple(
        sorted(i for i, b in available if b.anomaly_type == INTERFERENCE)
    )
    assert sample.population[FAULT] == tuple(
        sorted(i for i, b in available if b.anomaly_type == FAULT)
    )


def test_the_record_serialises_to_json() -> None:
    # spec: eval-004 -- it is committed before the first scored request, so
    # it has to be a file rather than something printed once. ai-004 already
    # paid for the alternative.
    written = json.loads(json.dumps(drawn().as_json()))

    assert written["seed"] == SEED
    assert written["per_kind"] == PER_KIND
    assert len(written["entries"]) == 2 * PER_KIND
    assert written["entries"][0].keys() == {"bundle_id", "kind", "scenario_type"}
    assert len(written["population"][INTERFERENCE]) == 20


def test_the_serialised_record_carries_no_bundle_contents() -> None:
    # spec: eval-004, NFR-405 -- the record is committed to the repository
    # and a bundle carries pseudonymised aircraft identifiers. Ids, kinds
    # and scenario types are what a reader needs to re-derive the draw; the
    # bundles themselves are in the database.
    written = json.dumps(drawn().as_json())

    assert "evidence" not in written
    assert "AC-" not in written
