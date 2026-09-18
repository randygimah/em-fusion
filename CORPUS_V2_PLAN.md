# Corpus v2 — the regeneration plan, recorded before it runs

Written 2026-09-18, **before generation**, because the thing this regeneration exists to fix is that
the first corpus's inputs were never written down.

## Base seeds

| Wave | Base seed |
|---|---|
| 1 | `1412660662` |
| 2 | `965530111` |
| 3 | `655209063` |

Drawn with `secrets` via `new_seed()`. A base seed is a value and not a secret: it is what makes a
batch reproducible, and the generator prints it either way. These are also written onto every run row
by `scn-008`, so the database is the durable record and this file is the human-readable one.

## Composition

**3 waves × 5 scenario types × 20 runs = 300 runs**, expected ids 241–540.

Every wave uses **one base seed across all five types**, so each run has a same-seed counterfactual in
every other arm — the same corpus window, the same aircraft, differing only in what was staged. The
first corpus had this for three of the five types; it did **not** have a `normal-baseline` twin for
each staged run, which is why `source_gap_ceiling.py` had to approximate a track-control with
`rf-sensor-fault` runs.

| Scenario type | Runs |
|---|---|
| `gnss-degradation` | 60 |
| `aircraft-coverage-gap` | 60 |
| `rf-sensor-fault` | 60 |
| `ambiguous-mixed-evidence` | 60 |
| `normal-baseline` | 60 |

## Fixed for every run

- **Run length 900 s.** One length throughout. The first corpus's runs 1–20 were 600 s and nothing
  recorded it; they carry two thirds of the track observations of every other run.
- **One generator.** Both `anom-014` (10 s minimum episode duration) and `scn-007` (floor of 5 staged
  aircraft) are active from run one. The first corpus spans three generator versions — runs 1–100
  predate `scn-006`'s airborne gate and name a mean of ~5 staged aircraft against <2 afterwards.
- Incident 300 s, radius 60 km, elevation 8 dB, narrowband — unchanged from the first corpus, which
  was homogeneous in these.

## What must not happen afterwards

**The old 240 runs are not deleted** (`db-007`), so the database will hold two corpora. Every
measurement must be restricted to ids 241–540 or selected by the base seeds above. Mixing them is
exactly the error that forced `scn-007`'s first floor measurement to be withdrawn — and that error
was made on a corpus that only spanned *two* generators.
