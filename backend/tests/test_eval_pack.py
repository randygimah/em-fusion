"""The scoring pack the second marker receives. Spec: eval-004.

The **second** of that item's two passes. The first drew the twenty packages
and was committed before anything was asked; this renders what a marker
reads, after `ai-012` has run.

**Three of the four things that make or break it are about what must not be
inferable.** The comparison is blind, and the rubric already concedes the
blinding is imperfect -- template prose is stylistically distinctive and a
marker may well recognise it. That residual threat is *stated* and accepted.
What must not be added to it is a **formatting** leak, because style is a
hint a marker sometimes acts on and a stray blank line is a perfect
classifier. So one renderer serves both arms, the A/B labels are reshuffled
per package, and the arm key is a separate artefact the marker never sees.

**The scored generation is taken by its ordinal.** Generation 1, fixed in
advance, and never substituted when it fell back -- swapping in generation 2
would delete every failure from the scored corpus and flatter the arm under
test. Taking it by row order instead would silently do the same thing on any
bundle whose rows were written in another order.

Nothing here touches a database or a model. Hypotheses arrive as a mapping
the caller has already read, following `eval-005`.
"""

from __future__ import annotations

import csv
import io
import re

import pytest

from app.ai.campaign import CampaignRecord, GenerationRecord
from app.ai.grounding import GroundingLedger
from app.ai.hypothesis import Hypothesis
from app.ai.service import ConfigurationError, GeneratorKind
from app.ai.template import generate
from app.db.hypotheses import GroundingStatus
from app.evaluation.pack import DIMENSIONS, build_pack
from tests.test_ai_template import fault_bundle, zone_bundle
from tests.test_eval_statistics import budget

HOSTED = GeneratorKind.HOSTED
TEMPLATE = GeneratorKind.TEMPLATE
SEED = 4242


# ------------------------------------------------------------------ the doubles


def a_hypothesis(title="Possible sensor fault", **kw) -> Hypothesis:
    base = generate(fault_bundle()).model_dump()
    base["hypothesis_title"] = title
    base.update(kw)
    return Hypothesis(**base)


def generation(bundle_id, ordinal, arm, row, **kw) -> GenerationRecord:
    kw.setdefault("generator", arm)
    kw.setdefault("grounding", GroundingStatus.PASSED)
    kw.setdefault("refusals", ())
    kw.setdefault("usage", None)
    kw.setdefault("seconds", 1.0)
    return GenerationRecord(
        bundle_id=bundle_id,
        ordinal=ordinal,
        requested_arm=arm,
        hypothesis_id=row,
        **kw,
    )


def a_record(generations) -> CampaignRecord:
    return CampaignRecord(
        generations=tuple(generations),
        skipped=(),
        budget=budget(),
        ledger=GroundingLedger(),
    )


def one_bundle_campaign(
    bundle_id=1, *, first_title="First generation", fell_back=False
):
    """One bundle, three model generations and one baseline, as ai-012 writes it."""
    rows = [
        generation(
            bundle_id,
            n,
            HOSTED,
            bundle_id * 10 + n,
            generator=TEMPLATE if (fell_back and n == 1) else HOSTED,
        )
        for n in (1, 2, 3)
    ] + [generation(bundle_id, 1, TEMPLATE, bundle_id * 10 + 9)]
    hypotheses = {
        bundle_id * 10 + 1: a_hypothesis(first_title),
        bundle_id * 10 + 2: a_hypothesis("Second generation"),
        bundle_id * 10 + 3: a_hypothesis("Third generation"),
        bundle_id * 10 + 9: a_hypothesis("The other wording"),
    }
    return rows, hypotheses


def packed(bundles=None, **kw):
    if bundles is None:
        bundles = [(1, fault_bundle()), (2, zone_bundle(tracks=False))]
    rows, hypotheses = [], {}
    for bundle_id, _ in bundles:
        r, h = one_bundle_campaign(bundle_id)
        rows += r
        hypotheses.update(h)
    kw.setdefault("record", a_record(rows))
    kw.setdefault("bundles", bundles)
    kw.setdefault("hypotheses", hypotheses)
    kw.setdefault("seed", SEED)
    return build_pack(**kw)


# ---------------------------------------------------- what the marker receives


def test_the_pack_holds_two_labelled_explanations_under_every_package() -> None:
    # spec: eval-004 -- 20 bundles x 2 arms = 40 items, paired within bundle
    # so bundle difficulty cancels out of the arm difference.
    pack = packed()

    assert pack.hypotheses_md.count("### Hypothesis A") == 2
    assert pack.hypotheses_md.count("### Hypothesis B") == 2
    assert len(pack.items) == 4


def test_the_arm_is_nowhere_in_what_the_marker_reads() -> None:
    # spec: eval-004 -- the whole comparison rests on this. The vocabulary is
    # read off the enum rather than spelled here, so a fourth arm cannot be
    # added without this noticing.
    #
    # Deliberately NOT checking for "model" or "baseline": an explanation may
    # legitimately say "a propagation model", and a check that forbade it
    # would fail on honest prose while catching nothing a marker could use.
    # The first version of this test did forbid them and failed on its own
    # fixture, which is the same defect one step earlier.
    pack = packed()

    for giveaway in [kind.value for kind in GeneratorKind] + ["generator", "arm key"]:
        assert giveaway not in pack.hypotheses_md.lower(), giveaway
        assert giveaway not in pack.score_sheet_csv.lower(), giveaway


def test_the_key_is_a_separate_artefact() -> None:
    # spec: eval-004, eval-006 -- joined only after both sheets are ingested,
    # so scores cannot be attributed to an arm during entry.
    pack = packed()

    rows = list(csv.DictReader(io.StringIO(pack.arm_key_csv)))

    assert len(rows) == 4
    assert {row["arm"] for row in rows} == {"hosted", "template"}
    assert all(row["item_id"] for row in rows)


def test_the_score_sheet_has_a_blank_column_per_dimension() -> None:
    # spec: eval-004, docs/scoring_rubric.md -- five dimensions in pass one
    # and two judgements in pass two, which is the 280 values quoted on the
    # consent form and must not drift from it.
    pack = packed()

    rows = list(csv.DictReader(io.StringIO(pack.score_sheet_csv)))

    assert len(rows) == 4
    for row in rows:
        for dimension in DIMENSIONS:
            assert row[dimension] == "", dimension


def test_the_score_sheet_and_the_key_join_on_the_same_item_id() -> None:
    # spec: eval-004, eval-006 -- ingest joins them, and two id schemes that
    # look alike would join silently wrong rather than fail.
    pack = packed()

    sheet = {r["item_id"] for r in csv.DictReader(io.StringIO(pack.score_sheet_csv))}
    key = {r["item_id"] for r in csv.DictReader(io.StringIO(pack.arm_key_csv))}

    assert sheet == key


# ------------------------------------------------------- what must not leak


def test_both_arms_are_rendered_by_the_same_code() -> None:
    # spec: eval-004 -- identical formatting across arms, including field
    # order and whitespace. Given identical content, the two renderings must
    # differ in nothing at all; anything else is a perfect classifier that
    # no amount of prose-style mitigation would cover.
    same = a_hypothesis("Identical text")
    rows, _ = one_bundle_campaign(1)
    hypotheses = {row.hypothesis_id: same for row in rows}

    pack = build_pack(
        record=a_record(rows),
        bundles=[(1, fault_bundle())],
        hypotheses=hypotheses,
        seed=SEED,
    )

    body = pack.hypotheses_md.split("### Hypothesis A")[1]
    first, second = body.split("### Hypothesis B")
    assert first.strip() == second.strip()


def test_the_labels_are_reshuffled_between_packages() -> None:
    # spec: eval-004, docs/scoring_rubric.md -- "A on one page has nothing to
    # do with A on the next". A fixed order would let a marker who worked out
    # one package work out all twenty.
    bundles = [(n, fault_bundle()) for n in range(1, 21)]
    rows, hypotheses = [], {}
    for bundle_id, _ in bundles:
        r, h = one_bundle_campaign(bundle_id)
        rows += r
        hypotheses.update(h)

    pack = build_pack(
        record=a_record(rows), bundles=bundles, hypotheses=hypotheses, seed=SEED
    )

    first_labels = {
        row["item_id"]: row["arm"]
        for row in csv.DictReader(io.StringIO(pack.arm_key_csv))
        if row["label"] == "A"
    }
    assert len(set(first_labels.values())) == 2, "every A is the same arm"


def test_the_shuffle_is_reproducible_from_its_number() -> None:
    # spec: eval-004, NFR-601 -- the key has to be re-derivable, or a lost
    # key loses the campaign rather than a file.
    assert packed().arm_key_csv == packed().arm_key_csv
    assert packed().arm_key_csv != packed(seed=SEED + 1).arm_key_csv


def test_the_evidence_package_is_rendered_for_the_marker_to_read_first() -> None:
    # spec: eval-004 -- the rubric's procedure is read the pack, then both
    # hypotheses, then score. A pack without its evidence cannot be scored on
    # dimension 1 at all.
    pack = packed()

    assert "## Evidence pack" in pack.hypotheses_md
    assert "Findings" in pack.hypotheses_md


# ---------------------------------------------- which generation is exported


def test_the_scored_generation_is_the_first_and_is_taken_by_its_ordinal() -> None:
    # spec: eval-004 -- fixed in advance. Taken by ordinal rather than by row
    # order, which would silently export a different generation on any bundle
    # whose rows were written in another order.
    rows, hypotheses = one_bundle_campaign(1, first_title="THE SCORED ONE")
    pack = build_pack(
        record=a_record(list(reversed(rows))),
        bundles=[(1, fault_bundle())],
        hypotheses=hypotheses,
        seed=SEED,
    )

    assert "THE SCORED ONE" in pack.hypotheses_md
    assert "Second generation" not in pack.hypotheses_md
    assert "Third generation" not in pack.hypotheses_md


def test_a_fallback_is_exported_as_what_the_arm_delivered() -> None:
    # spec: eval-004 -- if generation 1 is one the model failed and the
    # mechanical writer answered, that stands. Substituting generation 2
    # would delete every failure from the scored corpus and flatter the arm
    # under test -- an omission invisible in the results.
    rows, hypotheses = one_bundle_campaign(1, fell_back=True)
    pack = build_pack(
        record=a_record(rows),
        bundles=[(1, fault_bundle())],
        hypotheses=hypotheses,
        seed=SEED,
    )

    key = {
        r["item_id"]: r["arm"] for r in csv.DictReader(io.StringIO(pack.arm_key_csv))
    }
    assert sorted(key.values()) == ["hosted", "template"]
    assert len(pack.items) == 2, "the pair is still a pair"
    assert pack.hypotheses_md.count("Second generation") == 0


# ---------------------------------------------------------------- refusals


def test_a_bundle_with_only_one_arm_is_refused() -> None:
    # spec: eval-004 -- the design is paired within bundle, and an unpaired
    # item contributes a score to one arm with nothing to subtract it from,
    # which is worse than one bundle fewer.
    rows = [generation(1, 1, HOSTED, 11)]

    with pytest.raises(ConfigurationError, match="only one arm"):
        build_pack(
            record=a_record(rows),
            bundles=[(1, fault_bundle())],
            hypotheses={11: a_hypothesis()},
            seed=SEED,
        )


def test_a_bundle_in_the_campaign_but_not_supplied_is_refused() -> None:
    # spec: eval-004 -- exporting a hypothesis with no evidence pack beside
    # it gives the marker nothing to judge dimension 1 against.
    rows, hypotheses = one_bundle_campaign(1)

    with pytest.raises(ConfigurationError, match="no evidence bundle"):
        build_pack(record=a_record(rows), bundles=[], hypotheses=hypotheses, seed=SEED)


def test_a_missing_hypothesis_is_refused_rather_than_left_blank() -> None:
    # spec: eval-004 -- a blank item in a pack is one the marker scores as a
    # missing section, which the rubric says is a 1. A silently absent
    # hypothesis would therefore score its arm at the floor.
    rows, hypotheses = one_bundle_campaign(1)
    hypotheses.pop(11)

    with pytest.raises(ConfigurationError, match="no hypothesis"):
        build_pack(
            record=a_record(rows),
            bundles=[(1, fault_bundle())],
            hypotheses=hypotheses,
            seed=SEED,
        )


def test_the_item_count_is_reported_so_the_consent_figure_can_be_checked() -> None:
    # spec: eval-004, docs/scoring_rubric.md -- 280 values is quoted in the
    # participant information sheet and on the ethics form. A pack that
    # silently exported 18 bundles would ask for a different number than the
    # one consented to.
    pack = packed()

    assert pack.bundles == 2
    assert pack.items_per_bundle == 2
    assert pack.values_per_rater == 2 * 2 * len(DIMENSIONS)


def test_the_pack_s_shape_is_reportable_as_figures() -> None:
    # spec: eval-004, eval-003 -- the pack itself goes to a person, and the
    # numbers describing it go in the write-up: how many bundles, how many
    # items, and how many values one marker is being asked for. That last
    # one is what the consent form quotes.
    from app.evaluation.pack import as_json

    written = as_json(packed())

    assert written["bundles"] == 2
    assert written["items"] == 4
    assert written["values_per_rater"] == 20
    assert written["dimensions"] == list(DIMENSIONS)


def test_no_real_aircraft_identifier_can_reach_the_pack() -> None:
    # spec: eval-004, NFR-405, dal-004 -- the pack is a file handed to
    # another person. Identifiers in a bundle are pseudonyms by construction,
    # and this asserts the shape rather than trusting it.
    pack = packed()

    for token in re.findall(r"\b[0-9a-f]{6}\b", pack.hypotheses_md):
        pytest.fail(f"a bare 24-bit-looking address reached the pack: {token}")
