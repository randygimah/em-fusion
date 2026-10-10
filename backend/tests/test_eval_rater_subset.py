"""The second rater's ten packs, drawn by a declared rule. Spec: eval-011.

The first rater scored all twenty packs. The second scores ten, chosen by a
seeded draw within the scenario types and presented with the two bundle
kinds alternating, so no two look-alike packs sit side by side. Two things
make or break it. The draw must not be able to see a score, because the
first rater has seen theirs. And every item the second rater scores must
carry the id and label the first rater scored it under, or the two sheets
cannot be joined for agreement.

The draw and the renderer are looked up per test, so a missing piece fails
the tests that need it rather than the whole module at import.
"""

from __future__ import annotations

import importlib
import inspect
import random
from collections import Counter

import pytest

from app.ai.service import ConfigurationError
from app.evaluation.answers import pack_order
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_eval_pack import packed

INTERFERENCE = "possible_interference_zone"
FAULT = "possible_sensor_fault"
GNSS = "gnss-degradation"
RF = "rf-sensor-fault"
AMBIGUOUS = "ambiguous-mixed-evidence"
QUOTA = {GNSS: 5, RF: 3, AMBIGUOUS: 2}


def sampling():
    return importlib.import_module("app.evaluation.sampling")


def draw(entries, *, quota=QUOTA, seed=20261010):
    return sampling().draw_rater_subset(entries, quota=quota, seed=seed)


def entry(bundle_id, kind, scenario_type):
    return {"bundle_id": bundle_id, "kind": kind, "scenario_type": scenario_type}


def a_sample():
    """The committed sample's shape: 10 interference, 5 + 5 fault."""
    return (
        [entry(b, INTERFERENCE, GNSS) for b in range(248, 258)]
        + [entry(b, FAULT, RF) for b in range(300, 305)]
        + [entry(b, FAULT, AMBIGUOUS) for b in range(400, 405)]
    )


def kinds_of(order, entries):
    kind = {e["bundle_id"]: e["kind"] for e in entries}
    return [kind[b] for b in order]


# ----------------------------------------------------------- the declared rule


def test_the_seed_and_quota_are_the_ones_declared_before_the_draw() -> None:
    # spec: eval-011 -- SUBSET_SEED = 20261010, fixed in the spec before any
    # draw; 5 gnss-degradation, 3 rf-sensor-fault, 2 ambiguous-mixed-evidence.
    assert sampling().SUBSET_SEED == 20261010
    assert dict(sampling().SUBSET_QUOTA) == QUOTA


def test_the_draw_cannot_see_a_score() -> None:
    # spec: eval-011 -- a pure function of the sample entries, the quota and
    # the seed, and nothing else: no score sheet, no arm key.
    parameters = inspect.signature(sampling().draw_rater_subset).parameters
    assert list(parameters) == ["entries", "quota", "seed"]


def test_each_scenario_type_gives_its_quota() -> None:
    # spec: eval-011 -- 5 + 3 + 2 = ten packs.
    entries = a_sample()
    order = draw(entries)

    scenario = {e["bundle_id"]: e["scenario_type"] for e in entries}
    assert len(order) == 10
    assert len(set(order)) == 10
    assert Counter(scenario[b] for b in order) == Counter(QUOTA)


def test_five_interference_and_five_fault_keep_the_kind_balance() -> None:
    # spec: eval-011 -- the pre-registered bundle-kind balance holds.
    entries = a_sample()
    assert Counter(kinds_of(draw(entries), entries)) == {INTERFERENCE: 5, FAULT: 5}


def test_each_type_is_chosen_by_its_own_seeded_draw_over_ascending_ids() -> None:
    # spec: eval-011 -- random.Random(f'{seed}:{type}').sample over the
    # type's bundle ids in ascending order, so the draw is reproducible from
    # the spec's own words.
    entries = a_sample()
    random.Random(0).shuffle(entries)  # the input order must not matter
    order = set(draw(entries, seed=777))

    for scenario_type, k in QUOTA.items():
        ids = sorted(
            e["bundle_id"] for e in entries if e["scenario_type"] == scenario_type
        )
        expected = set(random.Random(f"777:{scenario_type}").sample(ids, k))
        assert expected <= order, scenario_type


def test_no_two_packs_of_one_kind_are_adjacent() -> None:
    # spec: eval-011 -- the kinds alternate, so the rater never meets a run
    # of near-duplicates.
    entries = a_sample()
    for seed in range(40):
        kinds = kinds_of(draw(entries, seed=seed), entries)
        assert all(a != b for a, b in zip(kinds, kinds[1:])), seed


def test_which_kind_leads_and_the_order_within_a_kind_come_from_the_seed() -> None:
    # spec: eval-011 -- both are seeded draws: across seeds each kind leads
    # sometimes, and the same seed always gives the same order.
    entries = a_sample()
    leaders = {kinds_of(draw(entries, seed=seed), entries)[0] for seed in range(40)}
    assert leaders == {INTERFERENCE, FAULT}
    assert draw(entries, seed=5) == draw(entries, seed=5)
    assert len({draw(entries, seed=seed) for seed in range(40)}) > 1


def test_the_order_within_a_kind_is_not_ascending_by_id() -> None:
    # spec: eval-011 -- the pack is sorted by bundle id today, which is what
    # grouped the look-alikes; the new order within a kind is drawn.
    entries = a_sample()
    kind = {e["bundle_id"]: e["kind"] for e in entries}
    shuffled = 0
    for seed in range(40):
        faults = [b for b in draw(entries, seed=seed) if kind[b] == FAULT]
        shuffled += faults != sorted(faults)
    assert shuffled > 0


def test_a_quota_larger_than_its_stratum_is_refused() -> None:
    # spec: eval-011 -- failure case.
    with pytest.raises(ConfigurationError, match=RF):
        draw(a_sample(), quota={GNSS: 5, RF: 6, AMBIGUOUS: 0})


def test_a_quota_naming_a_type_not_in_the_sample_is_refused() -> None:
    # spec: eval-011 -- failure case.
    with pytest.raises(ConfigurationError, match="normal-baseline"):
        draw(a_sample(), quota={GNSS: 5, RF: 3, "normal-baseline": 2})


def test_a_quota_whose_kinds_cannot_alternate_is_refused() -> None:
    # spec: eval-011 -- failure case: 5 interference against 2 fault leaves
    # interference packs side by side whatever the order.
    with pytest.raises(ConfigurationError, match="alternate"):
        draw(a_sample(), quota={GNSS: 5, RF: 1, AMBIGUOUS: 1})


def test_kinds_differing_by_one_can_alternate() -> None:
    # spec: eval-011 -- 3 against 2 alternates, starting with the larger kind.
    entries = a_sample()
    kinds = kinds_of(draw(entries, quota={GNSS: 3, RF: 1, AMBIGUOUS: 1}), entries)
    assert kinds == [INTERFERENCE, FAULT, INTERFERENCE, FAULT, INTERFERENCE]


# ------------------------------------------------------------- the rendering


def three_bundles():
    return [
        (1, fault_bundle()),
        (2, zone_bundle(tracks=False)),
        (3, fault_bundle()),
    ]


def test_an_explicit_order_renders_those_packs_in_that_order() -> None:
    # spec: eval-011 -- exactly those bundles, in that order, numbered
    # '1 of N' to 'N of N'.
    pack = packed(three_bundles(), order=[3, 2])

    assert pack_order(pack.hypotheses_md) == (3, 2)
    assert "## Evidence pack 00003 -- 1 of 2" in pack.hypotheses_md
    assert "## Evidence pack 00002 -- 2 of 2" in pack.hypotheses_md
    assert "00001" not in pack.hypotheses_md
    assert pack.bundles == 2


def test_the_subset_keeps_every_item_id_label_and_arm_of_the_full_pack() -> None:
    # spec: eval-011 -- labels are keyed on the shuffle seed and bundle id
    # alone, so each second-rater row joins a first-rater row on item_id.
    full = {item.item_id: item for item in packed(three_bundles()).items}
    subset = packed(three_bundles(), order=[3, 1]).items

    assert [item.item_id[:5] for item in subset] == ["00003", "00003", "00001", "00001"]
    for item in subset:
        twin = full[item.item_id]
        assert (item.label, item.arm, item.hypothesis) == (
            twin.label,
            twin.arm,
            twin.hypothesis,
        )


def test_the_score_sheet_follows_the_explicit_order() -> None:
    # spec: eval-011 -- score_sheet2 holds the pack's rows in the pack's order.
    pack = packed(three_bundles(), order=[2, 3])
    packs = [line.split(",")[1] for line in pack.score_sheet_csv.splitlines()[1:]]
    assert packs == ["00002", "00002", "00003", "00003"]


def test_the_preamble_and_glossary_cover_only_the_packs_in_the_subset() -> None:
    # spec: eval-011 -- a term met only in a dropped pack is not listed: a
    # subset renders exactly as a campaign of only those bundles would.
    subset = packed(three_bundles(), order=[1])
    alone = packed([(1, fault_bundle())])

    assert subset.hypotheses_md == alone.hypotheses_md


def test_without_an_order_the_pack_is_unchanged() -> None:
    # spec: eval-011 -- the first rater's pack is reproduced byte for byte.
    default = packed(three_bundles())
    assert pack_order(default.hypotheses_md) == (1, 2, 3)
    assert packed(three_bundles(), order=None).hypotheses_md == default.hypotheses_md


def test_an_order_naming_a_bundle_the_record_does_not_hold_is_refused() -> None:
    # spec: eval-011 -- failure case.
    with pytest.raises(ConfigurationError, match="99"):
        packed(three_bundles(), order=[1, 99])


def test_an_order_naming_a_bundle_twice_is_refused() -> None:
    # spec: eval-011 -- failure case.
    with pytest.raises(ConfigurationError, match="twice"):
        packed(three_bundles(), order=[2, 1, 2])
