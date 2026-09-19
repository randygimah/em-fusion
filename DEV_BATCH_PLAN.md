# The development batch — recorded before it runs

Written 2026-09-19, **before generation**, following `CORPUS_V2_PLAN.md`. The discipline is the
point: the reason corpus v1 is unrecoverable is that its inputs were printed to a screen and never
written down.

## Why this exists, and what it is not

The corpus was destroyed on 2026-09-19 — see `ops-004` and `docs/qa.md`. Corpus v2 is regenerable
from the three base seeds in `CORPUS_V2_PLAN.md`, and it will be, when `eval-001` is picked up and
generating runs is the work rather than a prerequisite to it.

**This is not that regeneration.** It is a small batch generated for one purpose: to develop the AI
hypothesis layer against *real* evidence bundles rather than ones I constructed myself. A real
bundle carries citations I did not choose, an uncertainty list whose most common entry is
"could not be measured", and prose assembled from measured values. A hand-built fixture agrees with
whatever the author expected, which is exactly the wrong thing to hand a model that is being tested
for overclaiming.

**No figure in the thesis may be measured from this batch.** It is a development fixture. It is
recorded here, and kept distinguishable in the database, so that it cannot quietly become evidence.

## Base seed

| Batch | Base seed |
|---|---|
| dev | `695081452` |

Drawn with `secrets` via `new_seed()`. Deliberately **not** one of corpus v2's three
(`1412660662`, `965530111`, `655209063`), so the two can never be confused by a query.

## Composition

**3 scenario types × 20 runs = 60 runs.** Twenty is the floor the batch entrypoint enforces, with a
stated reason — fewer cannot carry a per-type rate worth reporting — so twenty is what a batch is
even when the batch is not for reporting.

| Scenario type | Runs | Why this one |
|---|---|---|
| `normal-baseline` | 20 | **Required.** The baseline is what "normal" means, and the detectors refuse to build one from anything else. Also the silent control: it must produce zero bundles. |
| `rf-sensor-fault` | 20 | Produces `possible_sensor_fault` bundles — the kind whose track side is *not applicable* by design. |
| `gnss-degradation` | 20 | Produces `possible_interference_zone` bundles — the richer kind, spanning both data modes, carrying corroboration and a rate excess. |

The two arms left out are `aircraft-coverage-gap`, which has no rule and can only be silent, and
`ambiguous-mixed-evidence`, which is decided identically to `rf-sensor-fault` and exists as a
controlled comparison rather than as a distinct bundle shape. Neither adds a bundle the AI layer has
not already seen.

## Fixed for every run

Unchanged from corpus v2, so that a bundle from here has the same shape as a bundle from the
regenerated corpus later: run length 900 s, incident 300 s, radius 60 km, elevation 8 dB,
narrowband. `anom-014` and `scn-007` are active, as they have been since before v2.

## Keeping it out of the corpus

`measurements/corpus/_corpus.py` selected corpus v2 as *any run carrying a base seed*, which would
have swept this batch straight into every future measurement — the mixing hazard that module exists
to prevent, and the same class of error that forced `scn-007`'s first floor measurement to be
withdrawn. The predicate now pins v2's three seeds by value, and this batch is selectable on its own
with `CORPUS=dev`. Fixed **before** generating anything.
