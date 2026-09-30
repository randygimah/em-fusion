"""Metrics as files a write-up can cite. Spec: eval-003.

Everything before this ends in a committed log -- text a person reads and
retypes. This turns the figures into files a chart can be drawn from and a
thesis row can be traced back through, which is the item's whole claim:
*self-describing*, meaning nothing outside the file is needed to know what
produced the number.

**A seed reproduces the hours; a policy reproduces the figures.** The item's
failure case names "the seeds and parameters", and for the detection table
the parameters that matter are not the scenario's but the **detectors'** --
`anom-001`'s 6 dB threshold, `anom-014`'s minimum episode, `anom-010`'s gap
threshold and contact freshness, the three radii and `anom-005`'s
corroboration ratio. Change the threshold from 6 dB to 8 and every figure
moves with the base seed unchanged, so an export carrying seeds alone
satisfies the item as first written and is not reproducible. Both go out,
and a provenance record missing one of the settings named in
`REQUIRED_POLICIES` is **refused at construction** rather than exported
incomplete -- which turns the failure case from something to check into
something that cannot happen.

**Two provenance records, not one field.** The detection figures rest on a
corpus, its base seeds, its run count and those policies; the campaign
figures rest on a model id, the frozen generation parameters, the prompt
digest and `eval-004`'s sample seed and population. They are separately
dated besides. Flattened into one list of seeds, neither is reproducible.

**Traceability is a resolvable key and not a header comment.** A comment
line breaks a CSV parser, and the unit that actually travels into a write-up
is *one row* pasted into a table, which loses every line above it. So a
digest over the provenance record is the first column of every row and one
file resolves it -- `ai-004`'s pattern for the prompt, one item along.
Change any provenance field and the digest changes, so a stale row fails to
resolve rather than quietly citing the wrong corpus.

**No rate is exported without the counts behind it.** `eval-002` is careful
that a rate over an empty population is `None` and never 0.0, because a
precision of zero on an answer nobody gave reads as an answer always wrong.
A CSV writes `None` as an empty cell, and an empty cell is zero to a
spreadsheet and to a dataframe -- so the convention dies exactly here, which
is `anom-008`'s export dropping its band population one item along. A
sentinel token was rejected: it makes a numeric column non-numeric and the
item asks for charts. The counts beside the rate are `eval-005`'s own rule
and leave a blank cell unambiguous, since the denominator says whether it is
zero or unmeasured. `Table` refuses to exist otherwise.

**The export computes nothing.** It re-organises values and derives none:
no rounding, no percentages, no column totals. `eval-007`'s governing rule
for the scoring pack, here for a different reason -- an exporter that rounds
makes the quoted number differ from the computed one, and the CSV is what
gets quoted. The one join it does make is copying an arm's counts onto the
type row that cites its recall, so the row stands alone.

**Column names are derived, never retyped.** Rows are built by flattening
what each figure says it holds, so the header *is* the set of keys. A
hand-written header is precisely where `recall_per_run` becomes `recall` and
`eval-002`'s two-recalls guard evaporates at the one boundary it exists for.

Nothing here touches the filesystem: named files as text out, so a
measurement script decides where they land and the whole thing is checkable
without a temporary directory.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.service import _looks_like_a_credential
from app.evaluation.metrics import DetectionMetrics
from app.evaluation.statistics import CampaignStatistics

#: The settings without which the detection figures are not regenerable, and
#: therefore the floor a provenance record must carry. A **floor** rather
#: than a closed set: a rule that gains a knob should be able to record it
#: before this constant is updated, or the export becomes the thing holding
#: up the measurement. Argued for by name in the suite, on `ai-004`'s rule
#: for its egress exclusions, because a set that is merely whatever was
#: present when it was written cannot be added to deliberately.
REQUIRED_POLICIES: tuple[str, ...] = (
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
)

#: How much of the hash a row carries. Long enough that two records in one
#: project cannot collide, short enough to read off a printed table.
DIGEST_LENGTH = 12


class ExportError(ValueError):
    """A provenance record, a table or an export these files refuse."""


def _digest(payload: Mapping[str, Any]) -> str:
    """A stable short hash over a record's own content.

    Over the canonical JSON rather than over a formatted string, so the
    digest changes when a *value* changes and not when the rendering does.
    """
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:DIGEST_LENGTH]


def _flatten(node: Any, prefix: str = "") -> dict[str, str]:
    """One figure's own keys, as flat names and rendered cells.

    The separator is a dot here and is replaced with an underscore for a
    table's headers, so both files are produced from one traversal rather
    than from two that can disagree about what a field is called.
    """
    out: dict[str, str] = {}
    if isinstance(node, Mapping):
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}{key}."))
        return out
    name = prefix[:-1]
    if isinstance(node, (list, tuple)):
        out[name] = ";".join(str(item) for item in node)
    elif node is None:
        # The distinction `eval-002` refused to let 0.0 destroy. It survives
        # here only because the population is in the next column along.
        out[name] = ""
    else:
        out[name] = str(node)
    return out


def _underscored(node: Mapping[str, Any]) -> dict[str, str]:
    return {k.replace(".", "_"): v for k, v in _flatten(node).items()}


def _records(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """A table's entries flattened, with nested records aligned across them.

    A nested record that is absent on one entry and present on another
    flattens two ways -- to its own name carrying nothing, and to the
    expanded columns -- so the file gains a column blank on every row that
    duplicates what the expanded ones say, and that on the rows where the
    record really is absent reads as a missing *value* rather than a missing
    *record*. The shape is taken from the entries that do carry it, so
    nothing is inferred from what the columns happen to be called: `f1` and
    `f1_is_defined` are siblings, not a record and its expansion, and a rule
    written over names cannot tell the two apart.
    """
    shapes: dict[str, tuple[str, ...]] = {}
    for entry in entries:
        for key, value in entry.items():
            if isinstance(value, Mapping):
                shapes.setdefault(key, tuple(value))

    aligned: list[dict[str, str]] = []
    for entry in entries:
        filled = dict(entry)
        for key, inner in shapes.items():
            if filled.get(key) is None:
                filled[key] = {name: None for name in inner}
        aligned.append(_underscored(filled))
    return aligned


@dataclass(frozen=True, slots=True)
class DetectionProvenance:
    """What produced the detection figures, in full.

    `runs` is carried beside the seeds deliberately: a base seed derives a
    batch of a stated size (`scn-008`), so the seed alone does not say how
    many hours were scored.
    """

    corpus: str
    base_seeds: tuple[int, ...]
    runs: int
    policies: Mapping[str, str]
    measured_on: str

    def __post_init__(self) -> None:
        if not self.corpus.strip():
            raise ExportError(
                "the corpus is unnamed. Two corpora have existed in this "
                "project and one of them no longer does, so a figure that "
                "cannot say which it came from is a figure that cannot be "
                "checked."
            )
        if not self.base_seeds:
            raise ExportError(
                "no base seed was recorded. A corpus that cannot name the "
                "numbers it was generated from is exactly what the first "
                "three hundred hours were."
            )
        if self.runs < 1:
            raise ExportError(f"a corpus of {self.runs} runs scored nothing.")
        if not self.measured_on.strip():
            raise ExportError("no measurement date was recorded.")
        missing = [name for name in REQUIRED_POLICIES if name not in self.policies]
        if missing:
            raise ExportError(
                f"these detector settings were not recorded: {missing}. A seed "
                "reproduces the hours and a policy reproduces the figures -- "
                "change the deviation threshold and every number moves with "
                "the seed unchanged, so an export carrying seeds alone is not "
                "reproducible."
            )

    def as_json(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "corpus": self.corpus,
            "base_seeds": list(self.base_seeds),
            "runs": self.runs,
            "measured_on": self.measured_on,
            "policies": dict(sorted(self.policies.items())),
        }
        return {**record, "digest": _digest(record)}

    @property
    def digest(self) -> str:
        return str(self.as_json()["digest"])


@dataclass(frozen=True, slots=True)
class CampaignProvenance:
    """What produced the per-arm campaign figures, in full.

    `population` is half of what makes the draw repeatable: a seed alone
    reproduces a draw only against the same pool in the same order, which is
    `eval-004`'s own argument for recording it beside the sample.
    """

    model_id: str
    parameters: Mapping[str, Any]
    prompt_digest: str
    sample_seed: int
    population: Mapping[str, tuple[int, ...]]
    measured_on: str

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ExportError(
                "no model id was recorded. A campaign run against a model "
                "whose identity was not kept is a campaign to run again."
            )
        if not self.prompt_digest.strip():
            raise ExportError(
                "no prompt digest was recorded. The instructions are the "
                "experiment's largest variable, and two arms given different "
                "ones are not two answers to one question."
            )
        if not self.population:
            raise ExportError(
                "no population was recorded. The sample seed reproduces the "
                "draw only against the pool it drew from, in the order it "
                "saw it."
            )
        if not self.measured_on.strip():
            raise ExportError("no measurement date was recorded.")
        for key in self.parameters:
            # These go into a file that ends up in an appendix, which is a
            # boundary `ai-003`'s own guard was never asked about. Its check
            # is imported rather than written again, because two spellings of
            # "this looks like a secret" eventually disagree about one key.
            if _looks_like_a_credential(str(key)):
                raise ExportError(
                    f"{key!r} looks like a credential and these parameters are "
                    "written to a file. A key here is published, not merely "
                    "stored."
                )

    def as_json(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "model_id": self.model_id,
            "prompt_digest": self.prompt_digest,
            "sample_seed": self.sample_seed,
            "measured_on": self.measured_on,
            "parameters": {k: self.parameters[k] for k in sorted(self.parameters)},
            "population": {
                kind: list(ids) for kind, ids in sorted(self.population.items())
            },
        }
        return {**record, "digest": _digest(record)}

    @property
    def digest(self) -> str:
        return str(self.as_json()["digest"])


@dataclass(frozen=True, slots=True)
class Table:
    """One rectangle, and the declaration that makes its blanks readable.

    `counts_behind` maps a value that can be blank to the columns giving the
    population it was computed over. It is checked here rather than trusted,
    because the failure it prevents is silent: a blank cell with no
    denominator beside it reads as zero to every tool that will open this.
    """

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    counts_behind: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for column, counts in self.counts_behind.items():
            absent = [c for c in (column, *counts) if c not in self.columns]
            if absent:
                raise ExportError(
                    f"{self.name} exports {column!r} without the counts it was "
                    f"computed from: {absent} are not columns here. A blank "
                    "rate with no population beside it reads as zero."
                )
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ExportError(
                    f"{self.name} has a row of {len(row)} cells against "
                    f"{len(self.columns)} columns."
                )

    def as_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(self.columns)
        writer.writerows(self.rows)
        return out.getvalue()


@dataclass(frozen=True, slots=True)
class Export:
    """Named files as text. Nothing here knows where they will be written."""

    files: Mapping[str, str]
    tables: tuple[Table, ...]


def _table(
    name: str,
    records: Sequence[Mapping[str, str]],
    source: str,
    counts_behind: Mapping[str, tuple[str, ...]] | None = None,
) -> Table:
    """A rectangle over records that may not all carry the same keys.

    The column order is first-seen across every record rather than sorted,
    so a figure's own field order survives into the file.

    A record missing one of the columns raises rather than being blanked.
    Legitimate absence is `_records`' job and it fills the record's own
    shape, so anything still missing here is two entries that disagree about
    what they hold -- and blanking that writes a file where one row's value
    sits under another row's heading, which is unreadable and silent.
    """
    columns: list[str] = ["source"]
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)
    rows = tuple(
        tuple([source] + [record[key] for key in columns[1:]]) for record in records
    )
    return Table(
        name=name,
        columns=tuple(columns),
        rows=rows,
        counts_behind=dict(counts_behind or {}),
    )


_ARM_COUNTS = {
    "recall_per_run": ("detected", "runs"),
    "false_negative_rate": ("missed", "runs"),
    "latency_median_seconds": ("latency_measured", "latency_detections"),
    "latency_min_seconds": ("latency_measured", "latency_detections"),
    "latency_max_seconds": ("latency_measured", "latency_detections"),
    "track_side_recall_per_staged_aircraft": (
        "track_side_detected_aircraft",
        "track_side_staged_aircraft",
    ),
}

_TYPE_COUNTS = {
    "precision": ("correct", "claimed_runs"),
    "arm_recall_per_run": ("arm_detected", "arm_runs"),
    # F1's inputs are two rates rather than two counts, and both are columns
    # here, each with its own counts declared above.
    "f1": ("precision", "arm_recall_per_run"),
}

_FP_COUNTS = {"rate": ("runs_with_a_report", "runs")}

_CAMPAIGN_COUNTS = {
    "catch_rate": ("caught", "checked"),
    "retry_rate": ("refusals", "attempts"),
    "fallback_rate": ("fell_back", "generations"),
    "agreement_grounding": ("agreement_bundles",),
    "agreement_confidence": ("agreement_bundles",),
    "agreement_cited_kinds": ("agreement_bundles",),
}


def _detection_tables(metrics: DetectionMetrics, source: str) -> list[Table]:
    exported = metrics.as_json()

    arms = _table(
        "detection_arms.csv",
        _records(exported["arms"]),
        source,
        _ARM_COUNTS,
    )

    # The one join this module makes. F1 is a type's precision against an
    # *arm's* recall, and a row pasted into a table travels without the table
    # beside it -- so the arm's two counts are copied onto the type row,
    # verbatim from the arm and never recomputed.
    by_arm = {arm.scenario_type: arm for arm in metrics.arms}
    type_records = []
    for entry, record in zip(exported["types"], _records(exported["types"])):
        arms_behind = entry["arms"]
        arm = by_arm[arms_behind[0]] if len(arms_behind) == 1 else None
        record["arm_detected"] = "" if arm is None else str(arm.detected)
        record["arm_runs"] = "" if arm is None else str(arm.runs)
        type_records.append(record)

    types = _table("detection_types.csv", type_records, source, _TYPE_COUNTS)

    rates = _table(
        "detection_false_positives.csv",
        _records(exported["false_positive_rates"]),
        source,
        _FP_COUNTS,
    )

    confusion = _table(
        "detection_confusion.csv",
        [
            {"staged": staged, "reported": reported, "runs": str(runs)}
            for staged, row in sorted(exported["confusion"].items())
            for reported, runs in sorted(row.items())
        ],
        source,
    )
    return [arms, types, rates, confusion]


def _campaign_tables(statistics: CampaignStatistics, source: str) -> list[Table]:
    exported = statistics.as_json()
    return [
        _table(
            "campaign_arms.csv",
            _records(exported["arms"]),
            source,
            _CAMPAIGN_COUNTS,
        )
    ]


def _provenance_table(records: Mapping[str, Mapping[str, Any]]) -> Table:
    """One field per row, because the two records hold different fields.

    A wide file would be ragged across them and would gain a column every
    time either record learns a field, which changes the file's shape rather
    than its length.
    """
    rows: list[tuple[str, ...]] = []
    for name, record in sorted(records.items()):
        digest = str(record["digest"])
        for field_name, value in sorted(_flatten(record).items()):
            if field_name == "digest":
                continue
            rows.append((digest, name, field_name, value))
    return Table(
        name="provenance.csv",
        columns=("source", "record", "field", "value"),
        rows=tuple(rows),
    )


def export_metrics(
    *,
    detection: DetectionMetrics | None = None,
    detection_provenance: DetectionProvenance | None = None,
    campaign: CampaignStatistics | None = None,
    campaign_provenance: CampaignProvenance | None = None,
) -> Export:
    """Figures and their provenance as named files of text.

    Either half may be omitted, and neither half may be half-supplied:
    figures without provenance are figures nobody can check, and provenance
    without figures describes a measurement that is not here.
    """
    if detection is not None and detection_provenance is None:
        raise ExportError(
            "the detection figures were supplied with no provenance. A table "
            "nobody can trace back to the hours and settings behind it is the "
            "failure case this item names."
        )
    if campaign is not None and campaign_provenance is None:
        raise ExportError(
            "the campaign figures were supplied with no provenance. The model "
            "id and the frozen parameters are what make the run repeatable."
        )
    if detection is None and detection_provenance is not None:
        raise ExportError(
            "detection provenance was supplied with no figures to attach it to."
        )
    if campaign is None and campaign_provenance is not None:
        raise ExportError(
            "campaign provenance was supplied with no figures to attach it to."
        )
    if detection is None and campaign is None:
        raise ExportError("nothing to export: neither set of figures was supplied.")

    records: dict[str, Mapping[str, Any]] = {}
    payload: dict[str, Any] = {}
    tables: list[Table] = []

    if detection is not None and detection_provenance is not None:
        record = detection_provenance.as_json()
        records["detection"] = record
        payload["detection"] = detection.as_json()
        tables += _detection_tables(detection, str(record["digest"]))

    if campaign is not None and campaign_provenance is not None:
        record = campaign_provenance.as_json()
        records["campaign"] = record
        payload["campaign"] = campaign.as_json()
        tables += _campaign_tables(campaign, str(record["digest"]))

    tables.insert(0, _provenance_table(records))
    payload["provenance"] = dict(records)

    files = {"metrics.json": json.dumps(payload, indent=2, sort_keys=True) + "\n"}
    files.update({table.name: table.as_csv() for table in tables})
    return Export(files=files, tables=tuple(tables))


__all__ = [
    "DIGEST_LENGTH",
    "REQUIRED_POLICIES",
    "CampaignProvenance",
    "DetectionProvenance",
    "Export",
    "ExportError",
    "Table",
    "export_metrics",
]
