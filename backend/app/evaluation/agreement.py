"""Blind-score ingest and inter-rater agreement. Spec: eval-006.

The last step of the human scoring, and the only one that sees both raters'
sheets and the arm key together. It reads the two completed workbooks
(`eval-008`), measures how far the raters agree, and only then joins the
arm key to report each arm's scores.

**The order is the guarantee.** Agreement is computed by a function with no
parameter for the arm key, so nothing about which explanation came from
which generator can shape how agreement is measured. The per-arm summary is
a separate call that needs both sheets *and* the key.

**Joined on the item id, never on row order.** The second rater read ten
of the first rater's twenty packs in a different, alternating order
(`eval-011`); every item kept its id and label, so the id is the join.
Kappa is computed over the items both raters scored. The first rater's
other items are **single-rated**: reported on their own, never entered
into kappa and never averaged with a missing second score.

**Quadratic-weighted kappa over the whole 1-5 scale** (Cohen, 1968), as
pre-registered in `docs/scoring_rubric.md`: a 1-against-5 disagreement
costs sixteen times a 1-against-2. A scale point neither rater used adds
nothing to either marginal, so fixing the scale changes no value; it is
fixed so a value off it is refused rather than silently widening the
scale. When neither rater varies at all, chance agreement is total and the
statistic is 0/0: that is reported as `None`, never as perfect agreement.

**The interval resamples packs, not items.** The two explanations of one
pack were scored against the same evidence in the same sitting, so they
are not independent; resampling items would treat twenty correlated values
as twenty independent ones and narrow the interval falsely. A resample in
which the statistic is undefined is counted and excluded, and the count is
reported beside the interval. The seed and resample count were declared on
22 November 2026, before any kappa was computed from the real sheets.

**Adjudication is flagged here and decided by people.** The rubric's rule,
fixed in advance: scores are averaged for analysis; where two scores differ
by two or more the item is flagged and discussed, and both raters may
revise, with kappa reported on the pre-discussion scores. This module
reports the flags and computes from whatever sheets it is given, so the
pre-discussion figures and any post-discussion means come from the same
code.

Nothing here reaches a database or a model.
"""

from __future__ import annotations

import csv
import io
import random
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from openpyxl import load_workbook

from app.evaluation.pack import DIMENSIONS, JUDGEMENTS
from app.evaluation.workbook import ANCHORS, IDENTIFIERS, SCALE, SHEET

#: Scores this far apart on one dimension are flagged for discussion.
FLAG_GAP = 2

#: The interval's seed and resample count, declared before the real sheets
#: were read for agreement.
KAPPA_SEED = 20261122
KAPPA_RESAMPLES = 10_000
LEVEL = 0.95

ARMS = ("hosted", "template")


class AgreementError(ValueError):
    """Input this step refuses rather than scores around."""


# --- the statistic ----------------------------------------------------------


def quadratic_weighted_kappa(
    first: Sequence[int], second: Sequence[int], scale: Sequence[int] = SCALE
) -> float | None:
    """Cohen's kappa with quadratic weights, or None when it is 0/0."""
    if len(first) != len(second):
        raise AgreementError(f"{len(first)} scores against {len(second)}")
    if not first:
        raise AgreementError("no paired scores to compare")
    allowed = set(scale)
    off = [v for v in (*first, *second) if v not in allowed]
    if off:
        raise AgreementError(
            f"scores off the {min(scale)}-{max(scale)} scale: {sorted(set(off))}"
        )

    n = len(first)
    observed = sum((a - b) ** 2 for a, b in zip(first, second)) / n
    p_first, p_second = Counter(first), Counter(second)
    expected = sum(
        (p_first[i] / n) * (p_second[j] / n) * (i - j) ** 2
        for i in scale
        for j in scale
    )
    if expected == 0:
        return None
    return 1 - observed / expected


# --- reading -----------------------------------------------------------------


@dataclass(frozen=True)
class ScoreRow:
    item_id: str
    bundle_id: int
    label: str
    scores: Mapping[str, int]
    judgements: Mapping[str, str]


def read_score_sheet(data: bytes) -> tuple[ScoreRow, ...]:
    """One completed workbook, read by heading into field names."""
    book = load_workbook(io.BytesIO(data), data_only=True)
    if SHEET not in book.sheetnames:
        raise AgreementError(f"no {SHEET!r} sheet")
    rows = list(book[SHEET].iter_rows(values_only=True))
    if not rows:
        raise AgreementError("the sheet is empty")

    fields = [*DIMENSIONS, *JUDGEMENTS]
    expected = [*IDENTIFIERS, *(ANCHORS[name]["heading"] for name in fields)]
    header = [cell for cell in rows[0] if cell is not None]
    if header != expected:
        raise AgreementError(
            f"headings {header} are not the scoring sheet's {expected}"
        )

    read: list[ScoreRow] = []
    seen: set[str] = set()
    for raw in rows[1:]:
        if all(cell in (None, "") for cell in raw):
            continue
        item_id, pack, label, *values = raw[: len(expected)]
        item_id = str(item_id)
        if item_id in seen:
            raise AgreementError(f"{item_id} appears twice")
        seen.add(item_id)
        if item_id != f"{pack}-{label}":
            raise AgreementError(f"{item_id} is filed under pack {pack} label {label}")

        scores: dict[str, int] = {}
        for name, value in zip(DIMENSIONS, values[: len(DIMENSIONS)]):
            if value in (None, ""):
                raise AgreementError(f"{item_id}: {name} is blank")
            try:
                number = int(str(value).strip())
            except ValueError:
                raise AgreementError(f"{item_id}: {name} is {value!r}") from None
            if number not in SCALE:
                raise AgreementError(f"{item_id}: {name} is {number}, off the scale")
            scores[name] = number

        judgements: dict[str, str] = {}
        for name, value in zip(JUDGEMENTS, values[len(DIMENSIONS) :]):
            if value in (None, ""):
                raise AgreementError(f"{item_id}: {name} is blank")
            if value not in ANCHORS[name]["options"]:
                raise AgreementError(f"{item_id}: {name} is {value!r}")
            judgements[name] = str(value)

        read.append(ScoreRow(item_id, int(pack), str(label), scores, judgements))
    return tuple(read)


def read_arm_key(text: str) -> dict[str, str]:
    """The separately held key: one arm per item, one of each per pack."""
    key: dict[str, str] = {}
    per_pack: dict[str, list[str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        item, arm = row["item_id"], row["arm"]
        if arm not in ARMS:
            raise AgreementError(f"{item}: arm {arm!r}")
        if item in key:
            raise AgreementError(f"{item} appears twice in the key")
        key[item] = arm
        per_pack.setdefault(item.split("-")[0], []).append(arm)
    for pack, arms in per_pack.items():
        if sorted(arms) != sorted(ARMS):
            raise AgreementError(
                f"pack {pack} does not hold one item of each arm: {arms}"
            )
    return key


# --- agreement ----------------------------------------------------------------


@dataclass(frozen=True)
class DimensionAgreement:
    n: int
    kappa: float | None
    exact: int
    within_one: int


@dataclass(frozen=True)
class Agreement:
    double_scored: tuple[str, ...]
    single_rated: tuple[str, ...]
    dimensions: Mapping[str, DimensionAgreement]


@dataclass(frozen=True)
class Flag:
    item_id: str
    dimension: str
    first: int
    second: int


def _joined(
    first: Sequence[ScoreRow], second: Sequence[ScoreRow]
) -> tuple[list[tuple[ScoreRow, ScoreRow]], tuple[str, ...]]:
    by_id = {row.item_id: row for row in first}
    stray = sorted(row.item_id for row in second if row.item_id not in by_id)
    if stray:
        raise AgreementError(f"scored by the second rater only: {', '.join(stray)}")
    second_ids = {row.item_id for row in second}
    pairs = [(by_id[i], s) for i, s in sorted((r.item_id, r) for r in second)]
    single = tuple(sorted(i for i in by_id if i not in second_ids))
    return pairs, single


def agreement(first: Sequence[ScoreRow], second: Sequence[ScoreRow]) -> Agreement:
    """Agreement over the items both raters scored. Takes no arm key."""
    pairs, single = _joined(first, second)
    dimensions: dict[str, DimensionAgreement] = {}
    for name in DIMENSIONS:
        a = [p.scores[name] for p, _ in pairs]
        b = [q.scores[name] for _, q in pairs]
        gaps = [abs(x - y) for x, y in zip(a, b)]
        dimensions[name] = DimensionAgreement(
            n=len(pairs),
            kappa=quadratic_weighted_kappa(a, b),
            exact=sum(g == 0 for g in gaps),
            within_one=sum(g <= 1 for g in gaps),
        )
    return Agreement(tuple(p.item_id for p, _ in pairs), single, dimensions)


def flagged(first: Sequence[ScoreRow], second: Sequence[ScoreRow]) -> tuple[Flag, ...]:
    """Every double-scored value the raters put two or more points apart."""
    pairs, _ = _joined(first, second)
    return tuple(
        Flag(p.item_id, name, p.scores[name], q.scores[name])
        for p, q in pairs
        for name in DIMENSIONS
        if abs(p.scores[name] - q.scores[name]) >= FLAG_GAP
    )


@dataclass(frozen=True)
class Interval:
    low: float | None
    high: float | None
    resamples: int
    undefined: int


def pack_interval(
    first: Sequence[ScoreRow],
    second: Sequence[ScoreRow],
    dimension: str,
    *,
    seed: int = KAPPA_SEED,
    resamples: int = KAPPA_RESAMPLES,
    level: float = LEVEL,
) -> Interval:
    """A percentile bootstrap interval for kappa, resampling whole packs."""
    pairs, _ = _joined(first, second)
    packs: dict[int, list[tuple[int, int]]] = {}
    for p, q in pairs:
        packs.setdefault(p.bundle_id, []).append(
            (p.scores[dimension], q.scores[dimension])
        )
    ids = sorted(packs)
    rng = random.Random(f"{seed}:{dimension}")
    values: list[float] = []
    undefined = 0
    for _ in range(resamples):
        drawn = [pair for pack in rng.choices(ids, k=len(ids)) for pair in packs[pack]]
        k = quadratic_weighted_kappa([a for a, _ in drawn], [b for _, b in drawn])
        if k is None:
            undefined += 1
        else:
            values.append(k)
    if not values:
        return Interval(None, None, 0, undefined)
    values.sort()
    tail = (1 - level) / 2
    low = values[int(tail * (len(values) - 1))]
    high = values[int(round((1 - tail) * (len(values) - 1)))]
    return Interval(low, high, len(values), undefined)


# --- per arm --------------------------------------------------------------------


@dataclass(frozen=True)
class ArmScores:
    n: int
    mean: float | None
    distribution: Mapping[float, int]


@dataclass(frozen=True)
class ArmComparison:
    hosted: ArmScores
    template: ArmScores
    difference: float | None


@dataclass(frozen=True)
class ArmSummary:
    double_scored: Mapping[str, ArmComparison]
    first_rater: Mapping[str, ArmComparison]
    second_rater: Mapping[str, ArmComparison]
    judgements: Mapping[str, Mapping[str, Mapping[str, Mapping[str, int]]]]


#: The points an averaged score can fall on: two raters on a 1-5 scale.
HALF_POINTS: tuple[float, ...] = tuple(
    p / 2 for p in range(2 * min(SCALE), 2 * max(SCALE) + 1)
)


def _scores(values: Sequence[float], points: Sequence[float]) -> ArmScores:
    counts = Counter(values)
    stray = set(counts) - set(points)
    if stray:
        raise AgreementError(f"scores off the distribution's points: {sorted(stray)}")
    return ArmScores(
        n=len(values),
        mean=sum(values) / len(values) if values else None,
        distribution={point: counts.get(point, 0) for point in points},
    )


def _compare(
    rows: Mapping[str, Mapping[str, float]],
    key: Mapping[str, str],
    points: Sequence[float] = SCALE,
) -> dict[str, ArmComparison]:
    out: dict[str, ArmComparison] = {}
    for name in DIMENSIONS:
        by_arm = {
            arm: [rows[i][name] for i in sorted(rows) if key[i] == arm] for arm in ARMS
        }
        hosted = _scores(by_arm["hosted"], points)
        template = _scores(by_arm["template"], points)
        difference = (
            hosted.mean - template.mean
            if hosted.mean is not None and template.mean is not None
            else None
        )
        out[name] = ArmComparison(hosted, template, difference)
    return out


def arm_summary(
    first: Sequence[ScoreRow], second: Sequence[ScoreRow], key: Mapping[str, str]
) -> ArmSummary:
    """Each arm's scores, once both sheets are in.

    Three populations, never mixed: the double-scored items with the two
    raters' scores averaged; the first rater over everything they scored;
    the second rater over theirs. The hosted-minus-template difference is a
    difference of arm means within one population, and because every pack
    holds one item of each arm it equals the mean of the per-pack paired
    differences.
    """
    pairs, _ = _joined(first, second)
    missing = sorted(row.item_id for row in first if row.item_id not in key)
    if missing:
        raise AgreementError(f"not in the arm key: {', '.join(missing)}")

    averaged = {
        p.item_id: {n: (p.scores[n] + q.scores[n]) / 2 for n in DIMENSIONS}
        for p, q in pairs
    }
    judgements = {
        rater: {
            arm: {
                name: {
                    option: sum(
                        1
                        for r in rows
                        if key[r.item_id] == arm and r.judgements[name] == option
                    )
                    for option in ANCHORS[name]["options"]
                }
                for name in JUDGEMENTS
            }
            for arm in ARMS
        }
        for rater, rows in (("first", first), ("second", second))
    }
    return ArmSummary(
        double_scored=_compare(averaged, key, HALF_POINTS),
        first_rater=_compare({r.item_id: r.scores for r in first}, key),
        second_rater=_compare({r.item_id: r.scores for r in second}, key),
        judgements=judgements,
    )
