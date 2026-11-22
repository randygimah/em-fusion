"""Inter-rater agreement and the per-arm scores. Spec: eval-006.

Reads the two completed score sheets, computes agreement and the flagged
disagreements **before** the arm key is opened, and only then joins the key
to report each arm. Spends nothing and writes nothing but its own log.

The first rater's sheet is checksummed against the value
`build_rater2_pack.log` recorded when the second rater's pack was built, so
a first-rater score changed after the second rater's scores were seen
fails the run rather than passing into the result.

These are the **pre-discussion** figures. The rubric's adjudication rule
flags every value two or more points apart for discussion; kappa is
reported on these scores whatever the discussion changes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.evaluation.agreement import (
    FLAG_GAP,
    KAPPA_RESAMPLES,
    KAPPA_SEED,
    agreement,
    arm_summary,
    flagged,
    pack_interval,
    read_arm_key,
    read_score_sheet,
)
from app.evaluation.pack import DIMENSIONS, JUDGEMENTS

HERE = Path(__file__).parent
FIRST = HERE / "scoring_pack" / "score_sheet1.xlsx"
SECOND = HERE / "scoring_pack_rater2" / "score_sheet2_answered.xlsx"
KEY = HERE / "scoring_pack" / "arm_key.csv"

#: From `build_rater2_pack.log`, recorded on 10 October 2026.
FIRST_SHEET_SHA256_PREFIX = "eed3b6cf92fb651a"


def _f(value: float | None, places: int = 2) -> str:
    return (
        "  -  "
        if value is None
        else f"{value:+.{places}f}"
        if value < 0
        else f"{value:.{places}f}"
    )


def main() -> None:
    digest = hashlib.sha256(FIRST.read_bytes()).hexdigest()
    if not digest.startswith(FIRST_SHEET_SHA256_PREFIX):
        raise SystemExit(f"first rater's sheet changed since 10 October: {digest[:16]}")
    first = read_score_sheet(FIRST.read_bytes())
    second = read_score_sheet(SECOND.read_bytes())

    print(
        f"first rater  {FIRST.name}  {len(first)} items  sha256 {digest[:16]} (unchanged)"
    )
    print(f"second rater {SECOND.name}  {len(second)} items")

    result = agreement(first, second)
    packs = sorted({int(i.split("-")[0]) for i in result.double_scored})
    print(
        f"double-scored {len(result.double_scored)} items over {len(packs)} packs; "
        f"single-rated {len(result.single_rated)} (first rater only, never in kappa)"
    )
    print()
    print(
        "Agreement, pre-discussion: quadratic-weighted kappa, 95% interval resampling packs"
    )
    print(f"  seed {KAPPA_SEED}, {KAPPA_RESAMPLES} resamples")
    print(
        f"  {'dimension':20} {'n':>3} {'kappa':>6}  {'interval':>15}  {'undef':>5}  {'exact':>5}  {'within 1':>8}"
    )
    for name in DIMENSIONS:
        d = result.dimensions[name]
        iv = pack_interval(first, second, name)
        print(
            f"  {name:20} {d.n:>3} {_f(d.kappa):>6}  [{_f(iv.low):>5}, {_f(iv.high):>5}]  "
            f"{iv.undefined:>5}  {d.exact:>3}/{d.n}  {d.within_one:>4}/{d.n}"
        )

    flags = flagged(first, second)
    print()
    print(
        f"Flagged for discussion (scores {FLAG_GAP} or more apart): {len(flags)} of "
        f"{len(result.double_scored) * len(DIMENSIONS)} values"
    )
    for f in flags:
        print(f"  {f.item_id}  {f.dimension:20} first {f.first}  second {f.second}")

    # The key is opened only now, after both sheets are in and agreement is fixed.
    key = read_arm_key(KEY.read_text())
    summary = arm_summary(first, second, key)
    for title, population in (
        (
            "Double-scored items, the two raters averaged (pre-discussion)",
            summary.double_scored,
        ),
        ("First rater, every item scored", summary.first_rater),
        ("Second rater, every item scored", summary.second_rater),
    ):
        print()
        print(title)
        print(
            f"  {'dimension':20} {'hosted':>12} {'template':>12} {'hosted - template':>18}"
        )
        for name in DIMENSIONS:
            c = population[name]
            print(
                f"  {name:20} {_f(c.hosted.mean):>6} (n={c.hosted.n:>2}) {_f(c.template.mean):>6} (n={c.template.n:>2}) {_f(c.difference):>12}"
            )
        print(
            "  distribution, count at each point (averaged scores fall on half points):"
        )
        for name in DIMENSIONS:
            c = population[name]
            for arm, scores in (("hosted", c.hosted), ("template", c.template)):
                cells = "  ".join(
                    f"{p:g}:{n}" for p, n in scores.distribution.items() if n
                )
                print(f"    {name:20} {arm:8} {cells}")

    print()
    print("Pass two, counts")
    for rater, arms in summary.judgements.items():
        for arm, judged in arms.items():
            for name in JUDGEMENTS:
                counts = ", ".join(f"{k} {v}" for k, v in judged[name].items())
                print(f"  {rater:6} {arm:8} {name:22} {counts}")


if __name__ == "__main__":
    main()
