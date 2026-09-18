# Pre-registered, before batch 3 was measured — 2026-09-16

Batch 3: base seed 20260917, fixed generator, 60 runs. Batch 2's figures are the claim under test.

## What batch 2 said

| Radius | Staged caught | Controls fired | Best threshold (form 1) |
|---|---|---|---|
| 30 km | 5/20 | 2/20 | 1.79 |
| 45 km | 10/20 | 5/20 | 1.79 |
| 60 km | 16/20 | 9/20 | 1.58 |

## What is being tested, and how it can fail

1. **Out-of-sample, not re-fitted.** Batch 3 is scored at the thresholds batch 2 chose, not at
   thresholds refitted to batch 3. A threshold chosen on the data it is scored against is fitted to
   it, and would make any batch look like confirmation.
2. **Agreement** = batch 3's counts at the fixed thresholds fall inside batch 2's Wilson intervals,
   and the ordering across radii is preserved (60 km most sensitive, 30 km most specific).
3. **Disagreement** = batch 3 lands outside those intervals, or the ordering inverts. That would mean
   batch 2's curve was a property of its seed rather than of the method, and `anom-012` would need
   rewriting before it is built rather than after.
4. **Pooled estimate.** Whatever happens, the two batches are pooled to 40 pairs and the significance
   recomputed — the batch-2 p-values (0.407, 0.191, 0.048) are the figures most likely to move.

## Recorded in advance

The outcome is reported whichever way it falls, as `scn-006`'s prediction was. If batch 3 disagrees,
the correct response is to weaken `anom-012`'s claims, not to average the two batches until the
number looks better.
