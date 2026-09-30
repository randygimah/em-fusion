"""Metrics exported so a thesis table can be traced back. Spec: eval-003.

**Seeds do not reproduce these numbers.** The item's failure case names
"the seeds and parameters", and for the detection figures the parameters
that matter are the *detectors'* -- the deviation threshold, the minimum
episode, the gap threshold, the radii. Change the threshold from 6 dB to 8
and every figure moves with the base seed unchanged, so an export carrying
seeds alone is not reproducible. Both go out, and a provenance record
missing one is refused rather than exported incomplete.

**Traceability is a resolvable key, not a header comment.** A comment line
breaks a CSV parser, and what actually travels into a write-up is one row
pasted into a table, which loses every line above it. So a digest of the
provenance record is the first column of every row and one file resolves
it: change any provenance field and the digest changes, so a stale row
fails to resolve rather than quietly citing the wrong corpus.

**No rate is exported without the counts behind it.** `eval-002` is careful
that a rate over an empty population is `None` and never 0.0, and a CSV
writes `None` as an empty cell -- which a spreadsheet and a dataframe both
read as zero. The convention would die exactly here, which is `anom-008`'s
export dropping its band population one item along. A sentinel token was
rejected because it makes a numeric column non-numeric and the item asks
for charts; the counts beside the rate leave a blank cell unambiguous.

**The export computes nothing.** Every value it writes appears verbatim in
what it was handed -- no rounding, no percentages, no totals. `eval-007`'s
rule for the scoring pack, here because an exporter that rounds makes the
quoted number differ from the computed one, and the CSV is what is quoted.

**Column names are derived, never retyped.** A hand-written header is
precisely where `recall_per_run` becomes `recall` and `eval-002`'s
two-recalls guard evaporates at the one boundary it exists for.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from app.ai.service import GeneratorKind
from app.detection.control import REGISTER, audit
from app.evaluation.export import (
    DIGEST_LENGTH,
    REQUIRED_POLICIES,
    CampaignProvenance,
    DetectionProvenance,
    ExportError,
    Table,
    export_metrics,
)
from app.evaluation.metrics import RunOutcome, TrackSideRecall, compute
from app.evaluation.statistics import Agreement, ArmStatistics, CampaignStatistics

FAULT = "possible_sensor_fault"
INTERFERENCE = "possible_interference_zone"
BASELINE = "normal-baseline"
GNSS = "gnss-degradation"
SENSOR_FAULT = "rf-sensor-fault"
COVERAGE_GAP = "aircraft-coverage-gap"
AMBIGUOUS = "ambiguous-mixed-evidence"

POLICIES = {
    "BASELINE.window_h": "2",
    "RF-NOISE.metric": "power_dbm",
    "RF-NOISE.direction": "above",
    "RF-NOISE.threshold_db": "6.0",
    "RF-NOISE.minimum_episode_s": "10",
    "TRACK-GAP.threshold_s": "100",
    "TRACK-GAP.contact_fresh_within_s": "30",
    "TRACK-GAP.box": "49.0,54.0,3.0,11.0",
    "TRACK-CLUSTER.radius_km": "60.0",
    "SENSOR-FAULT.neighbour_radius_km": "150.0",
    "FUSION-SPATIAL.corroboration_threshold": "1.5",
    "FUSION-SPATIAL.excess_radius_km": "60.0",
}


def _detection_provenance(**over) -> DetectionProvenance:
    fields = {
        "corpus": "v2",
        "base_seeds": (1412660662, 965530111, 655209063),
        "runs": 300,
        "policies": dict(POLICIES),
        "measured_on": "2026-09-30",
    }
    fields.update(over)
    return DetectionProvenance(**fields)


def _campaign_provenance(**over) -> CampaignProvenance:
    fields = {
        "model_id": "gpt-4.1-2025-04-14",
        "parameters": {"temperature": 0.0, "max_tokens": 1200, "seed": 7},
        "prompt_digest": "a" * 64,
        "sample_seed": 20260918,
        "population": {FAULT: (247, 251), INTERFERENCE: (263, 271)},
        "measured_on": "2026-09-28",
    }
    fields.update(over)
    return CampaignProvenance(**fields)


def _counts(register=REGISTER):
    out = {}
    for key, producer in register.items():
        if producer.built:
            band = producer.background
            out[key] = band.low if band is not None else 0
    return out


def _metrics():
    outcomes = [
        RunOutcome(run_id="b1", scenario_type=BASELINE, staged=False),
        RunOutcome(run_id="b2", scenario_type=BASELINE, staged=False),
        RunOutcome(run_id="c1", scenario_type=COVERAGE_GAP),
        RunOutcome(run_id="c2", scenario_type=COVERAGE_GAP),
        RunOutcome(
            run_id="g1",
            scenario_type=GNSS,
            reported=(INTERFERENCE,),
            latency_seconds=40.0,
        ),
        RunOutcome(
            run_id="g2",
            scenario_type=GNSS,
            reported=(INTERFERENCE,),
            latency_seconds=60.0,
        ),
        RunOutcome(
            run_id="f1",
            scenario_type=SENSOR_FAULT,
            reported=(FAULT,),
            latency_seconds=20.0,
        ),
        RunOutcome(run_id="f2", scenario_type=SENSOR_FAULT),
        RunOutcome(run_id="a1", scenario_type=AMBIGUOUS, reported=(FAULT,)),
        RunOutcome(run_id="a2", scenario_type=AMBIGUOUS, reported=(FAULT,)),
    ]
    controls = {
        "b1": audit(run_id="b1", scenario_type=BASELINE, counts=_counts()),
        "b2": audit(run_id="b2", scenario_type=BASELINE, counts=_counts()),
    }
    return compute(
        outcomes,
        controls=controls,
        track_side={GNSS: TrackSideRecall(staged_aircraft=100, detected_aircraft=82)},
    )


def _statistics() -> CampaignStatistics:
    def arm(kind, **over):
        fields = dict(
            arm=kind,
            generations=60,
            bundles=20,
            skipped=0,
            checked=60,
            caught=0,
            catch_rate=0.0,
            attempts=60,
            refusals=0,
            refusals_by_category={},
            retry_rate=0.0,
            fell_back=0,
            fallback_rate=0.0,
            calls=60,
            prompt_tokens=326106,
            completion_tokens=25269,
            spent_usd=0.8544,
            unpriced_calls=0,
            cost_is_complete=True,
            seconds=334.2,
            agreement=Agreement(
                bundles=20, grounding=1.0, confidence=1.0, cited_kinds=0.95
            ),
        )
        fields.update(over)
        return ArmStatistics(**fields)

    return CampaignStatistics(
        arms=(
            arm(GeneratorKind.HOSTED),
            arm(
                GeneratorKind.TEMPLATE,
                generations=20,
                checked=20,
                attempts=20,
                calls=0,
                prompt_tokens=0,
                completion_tokens=0,
                spent_usd=0.0,
                seconds=0.008,
                catch_rate=0.0,
                retry_rate=0.0,
                fallback_rate=0.0,
                agreement=Agreement(
                    bundles=0, grounding=None, confidence=None, cited_kinds=None
                ),
            ),
        )
    )


def _export():
    return export_metrics(
        detection=_metrics(),
        detection_provenance=_detection_provenance(),
        campaign=_statistics(),
        campaign_provenance=_campaign_provenance(),
    )


def _rows(export, name) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(export.files[name])))


# --- the parameters that actually move the figures -------------------------


def test_the_export_carries_the_detector_policies_and_not_only_the_seeds() -> None:
    # spec: eval-003
    # A seed reproduces the hours; a policy reproduces the figures. Change the
    # deviation threshold and every number moves with the seed unchanged.
    exported = json.loads(_export().files["metrics.json"])
    recorded = exported["provenance"]["detection"]
    assert recorded["base_seeds"] == [1412660662, 965530111, 655209063]
    assert recorded["policies"]["RF-NOISE.threshold_db"] == "6.0"
    assert set(REQUIRED_POLICIES) <= set(recorded["policies"])


def test_a_provenance_missing_a_required_policy_is_refused() -> None:
    # spec: eval-003
    # Refused at construction rather than exported incomplete, which turns the
    # item's failure case from something to check into something that cannot
    # happen.
    short = {k: v for k, v in POLICIES.items() if k != "RF-NOISE.threshold_db"}
    with pytest.raises(ExportError, match="RF-NOISE.threshold_db"):
        _detection_provenance(policies=short)


def test_the_required_policies_are_the_settings_a_figure_moves_with() -> None:
    # spec: eval-003
    # Argued for by name rather than left as whatever was present when this was
    # written: a new detector adds a knob, and it has to be argued for here.
    assert set(REQUIRED_POLICIES) == {
        # what "normal" is measured over
        "BASELINE.window_h",
        # what counts as a deviation, and for how long
        "RF-NOISE.metric",
        "RF-NOISE.direction",
        "RF-NOISE.threshold_db",
        "RF-NOISE.minimum_episode_s",
        # what counts as a discontinuity, and over what ground
        "TRACK-GAP.threshold_s",
        "TRACK-GAP.contact_fresh_within_s",
        "TRACK-GAP.box",
        # the three radii and the one ratio the reportable rules turn on
        "TRACK-CLUSTER.radius_km",
        "SENSOR-FAULT.neighbour_radius_km",
        "FUSION-SPATIAL.corroboration_threshold",
        "FUSION-SPATIAL.excess_radius_km",
    }


def test_an_extra_policy_is_carried_rather_than_refused() -> None:
    # spec: eval-003
    # The required set is a floor. A rule that gains a knob should be able to
    # record it before this constant is updated, or the export becomes the
    # thing holding up the measurement.
    more = dict(POLICIES, **{"SOURCE-GAP.threshold": "unbuilt"})
    recorded = _detection_provenance(policies=more).as_json()["policies"]
    assert recorded["SOURCE-GAP.threshold"] == "unbuilt"


def test_the_two_provenance_records_are_separate() -> None:
    # spec: eval-003
    # Different inputs, different dates, different fields. One flattened record
    # would make neither reproducible.
    exported = json.loads(_export().files["metrics.json"])["provenance"]
    assert exported["detection"]["measured_on"] == "2026-09-30"
    assert exported["campaign"]["measured_on"] == "2026-09-28"
    assert exported["detection"]["digest"] != exported["campaign"]["digest"]


# --- traceability as a resolvable key --------------------------------------


def test_every_exported_row_carries_a_digest_that_resolves() -> None:
    # spec: eval-003
    # The unit that travels into a write-up is one row, not one file.
    export = _export()
    known = {row["source"] for row in _rows(export, "provenance.csv")}
    assert known
    for name in export.files:
        if not name.endswith(".csv") or name == "provenance.csv":
            continue
        rows = _rows(export, name)
        assert rows, name
        for row in rows:
            assert row["source"] in known, name


def test_the_digest_is_the_first_column_of_every_table() -> None:
    # spec: eval-003
    for table in _export().tables:
        assert table.columns[0] == "source", table.name


def test_changing_a_policy_changes_the_digest() -> None:
    # spec: eval-003
    # Which is the whole mechanism: a row exported under the old settings no
    # longer resolves, rather than resolving to the wrong ones.
    tighter = dict(POLICIES, **{"RF-NOISE.threshold_db": "8.0"})
    assert (
        _detection_provenance().digest != _detection_provenance(policies=tighter).digest
    )


def test_changing_a_seed_changes_the_digest() -> None:
    # spec: eval-003
    assert (
        _detection_provenance().digest
        != _detection_provenance(base_seeds=(1412660662, 965530111)).digest
    )


def test_reordering_the_seeds_changes_the_digest() -> None:
    # spec: eval-003
    # The order is the wave order, and `scn-008` records a run's index within
    # its batch, so the sequence is part of what the corpus is.
    assert (
        _detection_provenance().digest
        != _detection_provenance(base_seeds=(965530111, 1412660662, 655209063)).digest
    )


def test_the_provenance_file_is_long_so_two_unlike_records_share_a_shape() -> None:
    # spec: eval-003
    # Detection and campaign carry different fields, so a wide file would be
    # ragged. One field per row keeps it parseable by anything.
    rows = _rows(_export(), "provenance.csv")
    assert set(rows[0]) == {"source", "record", "field", "value"}
    detection = {r["field"]: r["value"] for r in rows if r["record"] == "detection"}
    assert detection["corpus"] == "v2"
    assert detection["policies.RF-NOISE.threshold_db"] == "6.0"


# --- no rate without its counts --------------------------------------------


def test_no_rate_is_exported_without_the_counts_behind_it() -> None:
    # spec: eval-003
    # Held over every table this actually produces, not over a fixture.
    for table in _export().tables:
        for column, counts in table.counts_behind.items():
            assert column in table.columns, (table.name, column)
            for count in counts:
                assert count in table.columns, (table.name, column, count)


def test_a_table_emitting_a_rate_without_its_counts_is_refused() -> None:
    # spec: eval-003
    with pytest.raises(ExportError, match="without the counts"):
        Table(
            name="x.csv",
            columns=("source", "recall_per_run"),
            rows=(("abc", "0.5"),),
            counts_behind={"recall_per_run": ("detected", "runs")},
        )


def test_a_blank_rate_is_readable_because_its_population_is_beside_it() -> None:
    # spec: eval-003, eval-002
    # The arm nobody generated: a blank cell and a denominator of 0. Without
    # the denominator, blank and 0.000 are the same cell to a reader.
    rows = {r["scenario_type"]: r for r in _rows(_export(), "detection_arms.csv")}
    unjudged = rows[COVERAGE_GAP]
    assert unjudged["recall_per_run"] == ""
    assert unjudged["runs"] == "2"
    assert unjudged["track_side_recall_per_staged_aircraft"] == ""
    assert unjudged["track_side_staged_aircraft"] == ""


def test_a_rate_of_zero_and_an_unmeasured_rate_are_different_cells() -> None:
    # spec: eval-003, eval-002
    # The distinction eval-002 refused to let 0.0 destroy, arriving at the one
    # boundary that would have destroyed it anyway.
    rows = {
        r["scenario_type"]: r for r in _rows(_export(), "detection_false_positives.csv")
    }
    assert rows[BASELINE]["rate"] == "0.0"
    arms = {r["scenario_type"]: r for r in _rows(_export(), "detection_arms.csv")}
    assert arms[BASELINE]["recall_per_run"] == ""


# --- the export computes nothing -------------------------------------------


def test_every_exported_value_appears_verbatim_in_what_was_handed_over() -> None:
    # spec: eval-003, eval-007
    # An exporter that rounds makes the quoted number differ from the computed
    # one, and the CSV is what gets quoted.
    metrics = _metrics()
    provenance = _detection_provenance()
    export = export_metrics(detection=metrics, detection_provenance=provenance)

    def tokens(node) -> set[str]:
        """Every name and every value in a record.

        Keys as well as values, because a key becoming a cell -- the
        confusion matrix's axes, the label saying what the latency is
        conditional on -- is re-organising and not computing, which is
        exactly the line this test is drawing.
        """
        if isinstance(node, dict):
            found = {str(k) for k in node}
            for item in node.values():
                found |= tokens(item)
            return found
        if isinstance(node, (list, tuple)):
            # A list becomes one delimited cell. Its elements are still
            # verbatim, so both spellings are allowed and neither is computed.
            joined = ";".join(str(item) for item in node)
            return {joined} | {t for item in node for t in tokens(item)}
        return {"" if node is None else str(node)}

    from_metrics = tokens(metrics.as_json())
    from_provenance = tokens(provenance.as_json())

    def is_verbatim(cell: str, allowed: set[str]) -> bool:
        """The cell itself, or a list rendered as one delimited cell.

        Both are things already present, re-organised. Anything else is a
        value this module invented, which is the line the item draws.
        """
        pieces = cell.split(";")
        return cell in allowed or (
            len(pieces) > 1 and all(piece in allowed for piece in pieces)
        )

    for table in export.tables:
        # The provenance file is long, so two of its columns hold *names* --
        # which record, which field. The rule is about values, and the names
        # are checked by the derived-columns tests instead.
        cells = (
            (lambda row: row[3:])
            if table.name == "provenance.csv"
            else (lambda row: row[1:])  # column 0 is the provenance digest
        )
        allowed = from_provenance if table.name == "provenance.csv" else from_metrics
        for row in table.rows:
            for cell in cells(row):
                if cell == "":
                    continue
                assert is_verbatim(cell, allowed), (table.name, cell)


def test_a_float_is_not_rounded_on_the_way_out() -> None:
    # spec: eval-003
    rows = {r["anomaly_type"]: r for r in _rows(_export(), "detection_types.csv")}
    fault = rows[FAULT]
    assert fault["precision"] == str(3 / 3)
    gnss_arm = {r["scenario_type"]: r for r in _rows(_export(), "detection_arms.csv")}
    assert gnss_arm[SENSOR_FAULT]["recall_per_run"] == str(1 / 2)
    assert gnss_arm[GNSS]["track_side_recall_per_staged_aircraft"] == str(82 / 100)


# --- column names are derived ----------------------------------------------


def test_no_column_anywhere_is_a_bare_recall() -> None:
    # spec: eval-003, eval-002
    # The guard eval-002 made mechanical, at the one boundary where a
    # hand-typed header would have undone it.
    for table in _export().tables:
        assert "recall" not in table.columns, table.name
        for column in table.columns:
            if "recall" in column:
                assert column.endswith("_per_run") or column.endswith(
                    "_per_staged_aircraft"
                ), column


def test_both_recalls_survive_the_export_on_one_row() -> None:
    # spec: eval-003, eval-002, anom-011
    rows = {r["scenario_type"]: r for r in _rows(_export(), "detection_arms.csv")}
    gnss = rows[GNSS]
    assert gnss["recall_per_run"] == "1.0"
    assert gnss["track_side_recall_per_staged_aircraft"] == str(82 / 100)
    # The per-aircraft figure keeps the record it came from in its name, so
    # the two cannot be read as one column's two spellings.
    assert "recall_per_staged_aircraft" not in gnss


def test_the_columns_are_the_exported_keys() -> None:
    # spec: eval-003
    # Derived from what the metrics say they hold, so a renamed field renames
    # a column rather than silently exporting the old name against new values.
    columns = {t.name: t.columns for t in _export().tables}
    assert "false_negative_rate" in columns["detection_arms.csv"]
    assert "latency_median_seconds" in columns["detection_arms.csv"]
    assert "latency_conditional_on" in columns["detection_arms.csv"]
    assert "f1_is_defined" in columns["detection_types.csv"]
    assert "agreement_cited_kinds" in columns["campaign_arms.csv"]


# --- the shapes ------------------------------------------------------------


def test_the_confusion_matrix_is_exported_one_cell_per_row() -> None:
    # spec: eval-003
    # A chart wants long, and a wide matrix gains a column every time a rule
    # is added, which changes the file's shape rather than its length.
    rows = _rows(_export(), "detection_confusion.csv")
    assert set(rows[0]) == {"source", "staged", "reported", "runs"}
    cell = next(
        r for r in rows if r["staged"] == GNSS and r["reported"] == INTERFERENCE
    )
    assert cell["runs"] == "2"


def test_a_type_row_carries_its_arms_counts_so_the_row_stands_alone() -> None:
    # spec: eval-003
    # F1 is a type's precision against an arm's recall, and a row pasted into a
    # table travels without the table beside it.
    rows = {r["anomaly_type"]: r for r in _rows(_export(), "detection_types.csv")}
    interference = rows[INTERFERENCE]
    assert interference["arms"] == GNSS
    assert interference["arm_detected"] == "2"
    assert interference["arm_runs"] == "2"
    assert interference["f1"] == "1.0"


def test_the_json_carries_the_metrics_unchanged() -> None:
    # spec: eval-003
    exported = json.loads(_export().files["metrics.json"])
    assert exported["detection"] == _metrics().as_json()
    assert exported["campaign"] == _statistics().as_json()


def test_the_file_names_are_stable() -> None:
    # spec: eval-003
    # A chart or a thesis build refers to these by name.
    assert set(_export().files) == {
        "metrics.json",
        "provenance.csv",
        "detection_arms.csv",
        "detection_types.csv",
        "detection_false_positives.csv",
        "detection_confusion.csv",
        "campaign_arms.csv",
    }


def test_only_what_was_supplied_is_exported() -> None:
    # spec: eval-003
    names = set(
        export_metrics(
            campaign=_statistics(), campaign_provenance=_campaign_provenance()
        ).files
    )
    assert names == {"metrics.json", "provenance.csv", "campaign_arms.csv"}


def test_every_csv_parses_back_to_what_was_written() -> None:
    # spec: eval-003
    for table in _export().tables:
        parsed = list(csv.reader(io.StringIO(table.as_csv())))
        assert parsed[0] == list(table.columns), table.name
        assert [tuple(r) for r in parsed[1:]] == list(table.rows), table.name


# --- refusals ---------------------------------------------------------------


def test_metrics_without_their_provenance_are_refused() -> None:
    # spec: eval-003
    with pytest.raises(ExportError, match="no provenance"):
        export_metrics(detection=_metrics())
    with pytest.raises(ExportError, match="no provenance"):
        export_metrics(campaign=_statistics())


def test_provenance_without_metrics_is_refused() -> None:
    # spec: eval-003
    with pytest.raises(ExportError, match="no figures"):
        export_metrics(detection_provenance=_detection_provenance())


def test_an_export_of_nothing_is_refused() -> None:
    # spec: eval-003
    with pytest.raises(ExportError, match="nothing to export"):
        export_metrics()


def test_a_credential_in_the_generation_parameters_is_refused() -> None:
    # spec: eval-003, ai-003
    # These parameters are written to a file that goes into an appendix, which
    # is a boundary ai-003's own guard was not asked about.
    with pytest.raises(ExportError, match="credential"):
        _campaign_provenance(parameters={"temperature": 0.0, "api_key": "sk-live"})


def test_a_blank_identifier_is_refused() -> None:
    # spec: eval-003
    with pytest.raises(ExportError, match="corpus"):
        _detection_provenance(corpus="  ")
    with pytest.raises(ExportError, match="model"):
        _campaign_provenance(model_id="")
    with pytest.raises(ExportError, match="prompt"):
        _campaign_provenance(prompt_digest="")


def test_a_corpus_with_no_seeds_or_no_runs_is_refused() -> None:
    # spec: eval-003, scn-008
    # A corpus that cannot name the numbers it came from is exactly what the
    # first three hundred hours were, and no log of them survived.
    with pytest.raises(ExportError, match="base seed"):
        _detection_provenance(base_seeds=())
    with pytest.raises(ExportError, match="runs"):
        _detection_provenance(runs=0)


def test_a_record_with_no_measurement_date_is_refused() -> None:
    # spec: eval-003
    # Both corpora and the campaign were superseded within eleven days of each
    # other. A figure that cannot say when it was taken cannot be placed.
    with pytest.raises(ExportError, match="date"):
        _detection_provenance(measured_on="")
    with pytest.raises(ExportError, match="date"):
        _campaign_provenance(measured_on="   ")


def test_each_record_can_be_asked_for_its_digest_directly() -> None:
    # spec: eval-003
    # What a measurement script prints beside the files it wrote.
    detection, campaign = _detection_provenance(), _campaign_provenance()
    assert detection.digest == detection.as_json()["digest"]
    assert campaign.digest == campaign.as_json()["digest"]
    assert len(campaign.digest) == DIGEST_LENGTH


def test_a_ragged_row_is_refused() -> None:
    # spec: eval-003
    # A short row silently shifts every cell after it into the wrong column,
    # and a CSV reader will not complain.
    with pytest.raises(ExportError, match="cells against"):
        Table(
            name="x.csv",
            columns=("source", "runs", "detected"),
            rows=(("abc", "2"),),
        )


def test_campaign_provenance_without_campaign_figures_is_refused() -> None:
    # spec: eval-003
    with pytest.raises(ExportError, match="no figures"):
        export_metrics(campaign_provenance=_campaign_provenance())


def test_a_sample_with_no_population_is_refused() -> None:
    # spec: eval-003, eval-004
    # The seed alone does not reproduce a draw: the population it drew from is
    # half of what makes it repeatable.
    with pytest.raises(ExportError, match="population"):
        _campaign_provenance(population={})
