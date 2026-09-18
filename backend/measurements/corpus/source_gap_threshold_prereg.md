# Pre-registered, before the sweep was run — 2026-09-18

`anom-006` was re-opened on the regenerated corpus because zone-level scoring moved from chance
(7:3 at 20 km) to **20 wins against 7 losses at 20 km**, about one in fifty by sign test. The item
records that this makes it **buildable to try and not known to be buildable**, and names the reason:
a sign test over matched pairs says the staged zone *tends to* beat its own control, and says nothing
about whether a threshold separates them on a single run. This is that measurement.

## The question, stated as the detector faces it

A detector sees **one run**, with no control, and must answer yes or no against a fixed bar. So:

> Is there a fixed pair (cluster radius, minimum cluster size, excess threshold) at which the
> strongest zone on an `aircraft-coverage-gap` run clears the bar and the strongest zone on a run
> that is not a coverage gap does not?

The statistic is the one the rule would actually receive: findings from `anom-010`, grouped by
`db-009` at a cluster radius, each group scored by `anom-012`'s rate excess over a 60 km disc with
the window taken as the span its own members cover — **byte-for-byte the machinery of
`source_gap_zone_scoring.py`**, so the two figures are comparable. The run's statistic is the
largest ratio among its groups meeting the size floor; a run with no such group does not fire.

## Populations

| Arm | n | Role |
|---|---|---|
| `aircraft-coverage-gap` | 60 | Positive |
| `normal-baseline` | 60 | **The decisive negative.** `anom-008` requires zero reportable anomalies here |
| `rf-sensor-fault` | 60 | Negative; the matched control the 20:7 was measured against |
| `rf-interference` | 60 | Negative, reported separately |
| `gnss-degradation` | 60 | Negative, reported separately — see caveat below |

## The split, and why there is one

The 20:7 was measured on this corpus. A threshold read off it and scored against it is fitted to it,
and would make any curve look like confirmation — the error `rate_excess_prereg.md` was written to
avoid. Corpus v2 came from three base seeds of 100 runs each, so:

- **Development**: base seeds `1412660662` and `965530111` — 40 positives, 40 quiet negatives.
- **Holdout**: base seed `655209063` — 20 positives, 20 quiet negatives. **Scored once, at the
  operating point development chose, and not re-entered.**

## The decision rule, fixed in advance

**Operating point** = the (radius, size floor, threshold) that maximises sensitivity on the
development positives **subject to zero false alarms on the development quiet arm**. Ties break
toward the larger size floor, then the higher threshold — the more conservative rule. Zero and not
"few": the quiet arm is `anom-008`'s control and a rule that fires there breaks a passing item.

**Separates** = that operating point, scored once on the holdout, gives sensitivity **≥ 0.25** with
**zero** holdout quiet-arm alarms. A rule catching a quarter of an arm that currently has no rule at
all is worth having; below that it is not worth the machinery.

**Does not separate** = no development operating point reaches 0.25 sensitivity at zero quiet-arm
alarms, or the holdout contradicts the one that did. **Then `anom-006` closes again on this
evidence**, the threat to validity on `eval-002` stands, and the correct next move is a generator
change, not another detector attempt.

## Recorded in advance

1. **The full sweep is reported whichever way it falls**, including the arms not in the decision
   rule, so the shape is visible even in failure. A sensitivity/false-alarm curve that fails a bar
   is a result; a sweep quietly rerun until a bar is met is not.
2. **`gnss-degradation` is a negative here but not a clean one.** That arm genuinely perturbs the
   track side — it rewrites reported staleness — so a firing there is a misattribution between two
   real effects rather than an invention. It is reported and excluded from the decision rule.
3. **Zero of 20 is not zero.** A holdout quiet arm with no alarms bounds the true rate at about 0.14
   upper 95% by Wilson, not at nothing. Any claim made from this measurement carries that bound.
4. **No threshold is chosen if the item closes.** The failure outcome is the item staying unbuilt,
   not a weaker bar.

---

## Change log

### 2026-09-18, after the collection pass, before any count was read

**The population table above named an arm that does not exist.** This project's five scenario types
are `normal-baseline`, `gnss-degradation`, `rf-sensor-fault`, `aircraft-coverage-gap` and
`ambiguous-mixed-evidence` (`app/scenario/incident.py`). There is no `rf-interference`: the RF
interference arm is `gnss-degradation`, which the prose in several documents calls "the interference
ones". The `rf-interference` column was therefore empty — `0/0` — and `ambiguous-mixed-evidence` was
omitted from the table altogether.

**The omitted arm is not a negative.** `tracks.py` gives `ambiguous-mixed-evidence` the same
`SUPPRESS` mode as `aircraft-coverage-gap`, so at a shared seed the two produce *identical* track
findings — verified exactly, not approximately. A firing there is detecting a real staged gap.

**`rf-sensor-fault` is not an independent negative either.** It perturbs nothing on the track side,
so its findings are identical to the quiet run at the same seed — also verified exactly. The clean
negative population is **60 distinct seeds, not 120 runs**, and no false-alarm rate here may be
quoted "of 120".

**The decision rule and the bar are unchanged, and were not re-entered.** Both refer only to the
`aircraft-coverage-gap` and `normal-baseline` arms, and both were identified correctly. The
correction changes what may be *reported*, not what was *tested*.

### Two defects in the first sweep script, fixed before the log of record was written

1. **Its print filter hid the decisive region.** It printed thresholds 1.0, 2.0 and 3.0, where the
   statistic is saturated and every arm fires identically, and never printed the region above 10
   where the arms actually part. The sweep had computed those rows and thrown them away.
2. **Its operating-point search accepted a rule that fires on nothing.** "Maximise sensitivity
   subject to zero false alarms" is satisfied vacuously at a size floor of 8, where no run of any
   arm produces a qualifying zone. It selected exactly that. The search now requires the rule to
   fire on at least one positive, and thresholds are taken from the observed values rather than
   from a fixed grid that can step over the only interesting point.
