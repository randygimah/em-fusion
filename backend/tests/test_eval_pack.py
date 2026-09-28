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
from dataclasses import replace

import pytest

from app.ai.campaign import GenerationRecord
from app.ai.hypothesis import Hypothesis
from app.ai.service import ConfigurationError, GeneratorKind
from app.ai.template import generate
from app.db.hypotheses import GroundingStatus
from app.detection.bundle import Uncertainty, UncertaintyKind
from app.evaluation.pack import BLINDING_GIVEAWAYS, DIMENSIONS, build_pack
from tests.test_ai_template import fault_bundle, verdict_of, zone_bundle

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
    kw.setdefault("generations", rows)
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
    # spec: eval-004 -- the whole comparison rests on this.
    #
    # The list is NOT the arm vocabulary, and getting that wrong twice is why
    # it is a named constant. "model" and "baseline" were excluded first,
    # because an explanation may honestly say "a propagation model". Then
    # this test checked all three GeneratorKind values, passed on fixtures
    # that never used the word "local", and fired on the first real pack --
    # where the baseline says "the local discontinuity rate could not be
    # measured" and the model says "caused by local equipment malfunction".
    # A check that fires on honest prose is not a stricter check, it is one
    # somebody switches off.
    pack = packed()

    for giveaway in [*BLINDING_GIVEAWAYS, "generator", "arm key"]:
        assert giveaway not in pack.hypotheses_md.lower(), giveaway
        assert giveaway not in pack.score_sheet_csv.lower(), giveaway
    assert (
        "local" not in BLINDING_GIVEAWAYS
    ), "an arm name that is also ordinary English cannot be searched for"


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
        generations=rows,
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
        generations=rows, bundles=bundles, hypotheses=hypotheses, seed=SEED
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
        generations=list(reversed(rows)),
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
        generations=rows,
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
            generations=rows,
            bundles=[(1, fault_bundle())],
            hypotheses={11: a_hypothesis()},
            seed=SEED,
        )


def test_a_bundle_in_the_campaign_but_not_supplied_is_refused() -> None:
    # spec: eval-004 -- exporting a hypothesis with no evidence pack beside
    # it gives the marker nothing to judge dimension 1 against.
    rows, hypotheses = one_bundle_campaign(1)

    with pytest.raises(ConfigurationError, match="no evidence bundle"):
        build_pack(generations=rows, bundles=[], hypotheses=hypotheses, seed=SEED)


def test_a_missing_hypothesis_is_refused_rather_than_left_blank() -> None:
    # spec: eval-004 -- a blank item in a pack is one the marker scores as a
    # missing section, which the rubric says is a 1. A silently absent
    # hypothesis would therefore score its arm at the floor.
    rows, hypotheses = one_bundle_campaign(1)
    hypotheses.pop(11)

    with pytest.raises(ConfigurationError, match="no hypothesis"):
        build_pack(
            generations=rows,
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


# ------------------------------------------- what a marker can actually read
#
# Spec: eval-007. Everything below is about the pack as a *document*. The
# first version rendered space-aligned plain text into a `.md` file, which is
# legible in an editor and reflows into one paragraph in anything that
# renders Markdown -- so the tests that matter here simulate the renderer
# rather than asserting on the source, which is what passed before.


def blocks(markdown: str) -> list[str]:
    """Markdown's own paragraph joining, applied.

    A renderer joins consecutive non-blank lines into one paragraph unless a
    line opens a block of its own -- a heading, a list item, a table row, a
    rule or a fence. This is the minimum needed to show the difference
    between a document that survives rendering and one that collapses, and
    it is the check the first version of the pack would have failed.
    """
    out: list[str] = []
    joining = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            joining = False
            continue
        opens_block = stripped.startswith(("#", "-", "*", "|", ">", "```", "---"))
        if joining and not opens_block:
            out[-1] = f"{out[-1]} {stripped}"
        else:
            out.append(stripped)
            joining = not opens_block
    return out


def findings_of(bundle):
    """Every evidence item except the one carrying the bundle's conclusion."""
    verdict = verdict_of(bundle)
    return [item for item in bundle.evidence if item is not verdict]


def test_no_two_findings_are_rendered_into_the_same_block() -> None:
    # spec: eval-007 (a) -- the defect, stated as the renderer sees it.
    #
    # Stated over *groups* rather than over findings, because the amended
    # design gathers one group's values on purpose -- that is the fix, not a
    # regression. What the original defect did was run findings from every
    # rule together into one paragraph, and that is what this still forbids.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    keys = {(f.rule_id, f.finding_type) for f in findings_of(bundle)}
    for block in blocks(pack_only):
        present = {
            key
            for key in keys
            if any(
                f.finding in block
                for f in findings_of(bundle)
                if (f.rule_id, f.finding_type) == key
            )
        }
        assert len(present) <= 1, f"{len(present)} rules share one block: {block!r}"


def test_no_line_sits_in_markdowns_ambiguous_indent() -> None:
    # spec: eval-007 (a) -- one to three spaces is neither a code block (four)
    # nor a list continuation, and is what the first version emitted.
    for line in packed().hypotheses_md.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        assert indent == 0 or indent >= 4, f"ambiguous indent {indent}: {line!r}"


def test_a_measurement_is_never_separated_from_its_source() -> None:
    # spec: eval-007 (d) -- the fault that is not cosmetic, restated for the
    # amended design.
    #
    # A hypothesis cites `RF-06:4`. The first pack rendered eight RF-NOISE
    # rows without naming a sensor on any of them, so evidence use -- the
    # first of five dimensions -- was scored against a pack its citations
    # could not be checked against. Factoring the shared sentence out of a
    # group is allowed; letting "13.43 dB" drift away from "RF-01:4" is not.
    #
    # Checked within the group's own block, because when every finding in a
    # group is worded identically the measurement belongs to all of them and
    # the sources are listed together beneath it.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    for finding in findings_of(bundle):
        if not finding.source:
            continue
        block = _block_for(pack_only, finding.rule_id, finding.finding_type)
        assert finding.source in block, f"{finding.source!r} not in its own block"
        for number in re.findall(r"\d+\.\d+", finding.finding):
            assert (
                number in block
            ), f"{number} rendered outside the block naming {finding.source!r}"


def _block_for(pack_only: str, rule_id: str, finding_type: str) -> str:
    """One group's block, found by the citation key that leads it."""
    heading = f"**{rule_id} / {finding_type}**"
    assert heading in pack_only, f"no block led by {heading}"
    rest = pack_only[pack_only.index(heading) + len(heading) :]
    # Cut at the next block's own citation key, not at the next bold text --
    # a single-finding block leads with its bolded source, which would
    # otherwise end the block before its content.
    following = re.search(r"\n\*\*[A-Z][A-Z0-9-]* / |\n### ", rest)
    return rest[: following.start()] if following else rest


def test_findings_are_grouped_by_the_citation_key() -> None:
    # spec: eval-007 (c) -- the (rule_id, finding_type) pair `ai-001` defines,
    # which is what `ai-008` resolves and what `ai-002` groups on. No new
    # vocabulary is invented here.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    expected = {(f.rule_id, f.finding_type) for f in findings_of(bundle)}
    for rule_id, finding_type in expected:
        assert f"{rule_id} / {finding_type}" in pack_only


def test_grouping_counts_the_findings_it_groups() -> None:
    # spec: eval-007 (c) -- nine identical lines become one heading carrying
    # the nine, which is the whole readability win.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    counted = {}
    for finding in findings_of(bundle):
        key = (finding.rule_id, finding.finding_type)
        counted[key] = counted.get(key, 0) + 1

    for (rule_id, finding_type), n in counted.items():
        heading = next(
            line
            for line in pack_only.splitlines()
            if f"{rule_id} / {finding_type}" in line
        )
        assert str(n) in heading, f"{heading!r} does not carry its count of {n}"
        # The citation key leads the block, because checking a citation
        # against the pack is the first scored dimension.
        assert heading.lstrip().startswith("**"), heading


def test_grouping_does_not_replace_detail_with_summary() -> None:
    # spec: eval-007 -- the item's hard constraint, and the one risk in
    # fixing readability at all.
    #
    # A pack that summarised its own findings would have done part of the
    # work dimension 1 scores, deflating the difference between the arms in
    # the direction that flatters the weaker one. So every finding is still
    # listed individually under its counted heading; only the scan cost goes.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    for finding in findings_of(bundle):
        assert pack_only.count(finding.finding) >= 1, f"{finding.finding!r} dropped"


def test_the_bundles_own_conclusion_leads_the_pack() -> None:
    # spec: eval-007 (b) -- the claim the pack is about sat tenth of nineteen.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    verdict = verdict_of(bundle)
    lead = pack_only.index(verdict.finding)
    for finding in findings_of(bundle):
        assert lead < pack_only.index(
            finding.finding
        ), f"{finding.finding!r} is rendered before the bundle's own conclusion"


def test_a_bundle_with_no_conclusion_of_its_own_is_refused() -> None:
    # spec: eval-007 -- `ai-002`'s exactly-one rule, which is `evb-002`'s
    # exactly-one-row rule a layer up. Rendered with an arbitrary lead, the
    # marker would read whichever item the heap put first as the claim.
    bundle = zone_bundle()
    without = bundle.with_evidence(
        [item for item in bundle.evidence if item.finding_type != bundle.anomaly_type]
    )

    with pytest.raises(ConfigurationError, match="conclusion"):
        packed(bundles=[(1, without)])


def test_a_bundle_with_two_conclusions_is_refused() -> None:
    # spec: eval-007 -- the other direction of the same rule.
    bundle = zone_bundle()
    verdict = verdict_of(bundle)
    doubled = bundle.with_evidence(list(bundle.evidence) + [verdict])

    with pytest.raises(ConfigurationError, match="conclusion"):
        packed(bundles=[(1, doubled)])


def test_repeated_uncertainties_are_counted_rather_than_repeated() -> None:
    # spec: eval-007 (e) -- the real pack carried the same RF-07 sentence
    # three times, verbatim.
    # Constructed rather than taken off a fixture: the real pack carried
    # three byte-identical RF-07 sentences and the fixtures carry none, so a
    # test reading the fixture would skip and prove nothing -- which is what
    # the first version of this test did.
    raised = Uncertainty(
        kind=UncertaintyKind.MEASURED_NEGATIVE,
        statement=(
            "a deviation on channel 4 of RF-07 lasted 1 reading(s), under the "
            "10 s minimum, so it was observed and not called an event."
        ),
        subject="RF-07:4",
    )
    alone = Uncertainty(
        kind=UncertaintyKind.NOT_MEASURABLE,
        statement="the local discontinuity rate could not be measured.",
        subject="60 km disc",
    )
    doubled = replace(
        zone_bundle(), known_uncertainties=(raised, raised, raised, alone)
    )
    pack = packed(bundles=[(1, doubled)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    assert pack_only.count(raised.statement) == 1
    assert "3" in next(
        line for line in pack_only.splitlines() if raised.statement in line
    ), "a de-duplicated uncertainty must say how many times it was raised"
    # and the one raised once is still there, unadorned.
    assert pack_only.count(alone.statement) == 1


def test_every_pack_says_where_it_sits_in_the_run() -> None:
    # spec: eval-007 (f) -- a marker working through twenty needs to know
    # which one they are on without counting headings.
    pack = packed()

    assert "1 of 2" in pack.hypotheses_md
    assert "2 of 2" in pack.hypotheses_md


def test_the_evidence_pack_renders_the_same_whichever_arm_got_label_a() -> None:
    # spec: eval-007 -- the restructure is exactly where a formatting leak
    # could be introduced by accident, and a formatting difference is a
    # perfect classifier where prose style is only a hint (`eval-004`).
    bundles = [(1, zone_bundle())]
    one = packed(bundles=bundles, seed=1)
    other = packed(bundles=bundles, seed=2)

    assert one.hypotheses_md.split("### Hypothesis")[0] == (
        other.hypotheses_md.split("### Hypothesis")[0]
    )


# ------------------------------------------------ the pack after a human read it
#
# Spec: eval-007, amended. Valid Markdown turned out to be necessary and
# nowhere near sufficient: fourteen rows repeating one sentence are a wall
# whether or not each sits in its own table row. What follows is about the
# *text*, not the structure.


def test_a_group_states_its_shared_sentence_once() -> None:
    # spec: eval-007 -- fourteen findings carry one sentence and fourteen
    # values. The sentence is what the eye has to re-read, so it is factored
    # into the group heading and each row keeps only what differs.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    # Grouped on the citation key, not the rule: TRACK-GAP carries both
    # the discontinuities and the rate excess, which is the collapse the
    # two-part key exists to prevent -- and reading it wrong here made
    # this test skip, which proves nothing.
    groups: dict[tuple[str, str], list[str]] = {}
    for finding in findings_of(bundle):
        groups.setdefault((finding.rule_id, finding.finding_type), []).append(
            finding.finding
        )
    repeated = [
        texts for texts in groups.values() if len(texts) > 1 and len(set(texts)) == 1
    ]
    assert repeated, "fixture has no group of identically worded findings"
    identical = set(repeated[0])

    sentence = identical.pop()
    assert pack_only.count(sentence) == 1, (
        f"{len(repeated)} findings share one sentence and it is printed "
        f"{pack_only.count(sentence)} times"
    )


def test_a_factored_group_still_names_every_source() -> None:
    # spec: eval-007 -- factoring removes repeated words, never evidence.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    for finding in findings_of(bundle):
        if finding.source:
            assert finding.source in pack_only, f"{finding.source!r} dropped"


def test_a_factored_group_still_carries_every_value() -> None:
    # spec: eval-007 -- the values are the evidence. Factoring the sentence
    # around them must leave every one of them on the page.
    deviations = [
        _rf_finding("RF-01:4", "power_dbm deviated by 13.43 dB at its peak"),
        _rf_finding("RF-01:4", "power_dbm deviated by 10.62 dB at its peak"),
        _rf_finding("RF-02:4", "power_dbm deviated by 8.37 dB at its peak"),
    ]
    bundle = zone_bundle()
    bundle = bundle.with_evidence(list(bundle.evidence) + deviations)
    pack_only = packed(bundles=[(1, bundle)]).hypotheses_md.split("### Hypothesis")[0]

    for value in ("13.43", "10.62", "8.37"):
        assert value in pack_only, f"{value} was factored away"
    # ...and the sentence around them exactly once.
    assert pack_only.count("power_dbm deviated by") == 1


def test_the_pack_introduces_no_number_of_its_own() -> None:
    # spec: eval-007 -- the constraint that replaced "never summarise", and
    # the reason it is mechanical: a minimum, a mean or a range is a
    # synthesis an explanation could otherwise be credited for. The pack
    # re-organises values and computes none.
    #
    # Counts of items the pack itself lists are the one exception, because
    # the reader could count them and a marker checking "nine aircraft"
    # against the pack needs to be able to.
    bundle = zone_bundle()
    pack = packed(bundles=[(1, bundle)])
    pack_only = pack.hypotheses_md.split("### Hypothesis")[0]

    sources = " ".join(
        [item.finding for item in bundle.evidence]
        + [item.source for item in bundle.evidence]
        + [u.statement for u in bundle.known_uncertainties]
        + [u.subject for u in bundle.known_uncertainties]
        + [bundle.subject, str(bundle.affected_channels), str(bundle.time_window)]
    )
    allowed = set(re.findall(r"\d+(?:\.\d+)?", sources))
    # Every group size, and every count of repeats, is countable from the page.
    allowed |= {str(n) for n in range(0, len(bundle.evidence) + 2)}
    # The heading carries the pack's identifier and its position, which are
    # names rather than measurements -- and the marker needs the identifier
    # to find the right row on the score sheet.
    # Scoped to the evidence. The heading carries the pack's identifier and
    # position and the table above it carries the window -- names and bundle
    # metadata, not measurements, and the marker needs the identifier to
    # find the right row on the score sheet.
    body = pack_only[pack_only.index("### The conclusion") :]

    for number in re.findall(r"\d+(?:\.\d+)?", body):
        assert (
            number in allowed
        ), f"the pack introduced {number!r}, computed from nothing"


def test_near_identical_uncertainties_collapse_to_one_statement() -> None:
    # spec: eval-007 -- six sentences differing in one sensor name were six
    # lines in the real pack. Exact de-duplication does not touch them,
    # because they are not exactly equal.
    statement = (
        "a deviation on channel 4 of {} lasted 1 reading(s), under the 10 s "
        "minimum, so it was observed and not called an event."
    )
    raised = tuple(
        Uncertainty(
            kind=UncertaintyKind.MEASURED_NEGATIVE,
            statement=statement.format(sensor),
            subject=sensor,
        )
        for sensor in ("RF-01", "RF-02", "RF-02", "RF-03", "RF-03", "RF-03")
    )
    bundle = replace(zone_bundle(), known_uncertainties=raised)
    pack_only = packed(bundles=[(1, bundle)]).hypotheses_md.split("### Hypothesis")[0]

    assert pack_only.count("under the 10 s") == 1, "the shared sentence repeats"
    for sensor in ("RF-01", "RF-02", "RF-03"):
        assert sensor in pack_only, f"{sensor} was factored away"


def test_uncertainties_that_share_nothing_are_left_alone() -> None:
    # spec: eval-007 -- factoring fires only on genuinely shared text.
    # Forced onto unrelated sentences it would produce a heading that is the
    # empty string and a list of whole sentences pretending to be values.
    unrelated = (
        Uncertainty(
            kind=UncertaintyKind.NOT_MEASURABLE,
            statement="the local discontinuity rate could not be measured here.",
            subject="60 km disc",
        ),
        Uncertainty(
            kind=UncertaintyKind.NOT_MEASURABLE,
            statement="no baseline existed for this cell, so it was not judged.",
            subject="RF-09:2",
        ),
    )
    bundle = replace(zone_bundle(), known_uncertainties=unrelated)
    pack_only = packed(bundles=[(1, bundle)]).hypotheses_md.split("### Hypothesis")[0]

    for uncertainty in unrelated:
        assert uncertainty.statement in pack_only


def test_a_group_of_one_is_not_dressed_up_as_a_group() -> None:
    # spec: eval-007 -- a single finding has no shared sentence to factor,
    # and a heading plus a one-row table is three lines doing one line's job.
    bundle = zone_bundle()
    pack_only = packed(bundles=[(1, bundle)]).hypotheses_md.split("### Hypothesis")[0]

    single = [
        f
        for f in findings_of(bundle)
        if sum(
            1
            for other in findings_of(bundle)
            if (other.rule_id, other.finding_type) == (f.rule_id, f.finding_type)
        )
        == 1
    ]
    if not single:
        pytest.skip("fixture has no single-finding group")
    for finding in single:
        assert finding.finding in pack_only


def _rf_finding(source: str, finding: str):
    """An observed RF item, for building a group with shared wording."""
    from app.detection.bundle import DataMode, EvidenceItem, Grounding

    base = next(i for i in zone_bundle().evidence if i.refs)
    return EvidenceItem(
        source=source,
        finding=finding,
        rule_id="RF-NOISE",
        finding_type="rf_noise_deviation",
        data_mode=DataMode.SYNTHETIC,
        started_at=base.started_at,
        ended_at=base.ended_at,
        grounding=Grounding.OBSERVED,
        refs=base.refs,
    )
