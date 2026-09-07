"""Deterministic value derivation from a run's seed. Spec: scn-001.

Every invented number in a scenario comes from here, and the shape of these
three functions is what makes `scn-001`'s property hold by construction rather
than by care.

**Keyed derivation, not sequential draws.** A `random.Random(seed)` drawn from
in a loop produces a stream that is a function of the *order* the loop happened
to run in, so reordering the grid, generating two sensors in parallel, or
inserting one extra draw during development silently changes every value after
it. Here each value is derived from the seed and the coordinates of the thing
being valued -- sensor, channel, tick -- so no cell can see any other cell, and
the third leak `scn-001` names cannot occur. It also means a single cell can be
recomputed later without replaying the run that produced it, which is what
`scn-003`'s batch and any future spot-check need.

**`hashlib`, not the built-in `hash`.** Python salts `hash()` per process, so a
stream derived through it is identical everywhere within one run of the test
suite and different the next morning -- reproducible exactly long enough to be
trusted. BLAKE2b is unsalted here by construction and stable across versions
and platforms. It is used as a deterministic mixer rather than for any security
property.

**`secrets` appears here and nowhere else in the package.** Drawing a seed is
the one legitimate use of entropy in a deterministic generator, because the
value it produces immediately becomes a recorded *input* to the run rather than
an unrecorded influence on its output. `new_seed` is bounded by the width of
`scenario_runs.seed` so a drawn seed cannot fail at insert time in the middle
of a batch, long after the value was chosen.
"""

from __future__ import annotations

import hashlib
import math
import secrets

#: The widest value `scenario_runs.seed` can hold: the column is a 32-bit
#: signed integer (`db-001`), and a seed that does not round-trip through the
#: run record is a seed that cannot reproduce the run.
SEED_MAX = 2**31 - 1

#: ASCII unit separator. Joining keys with a character that cannot occur in a
#: sensor identifier or a decimal number keeps ("RF-1", 12) and ("RF-11", 2)
#: distinct -- concatenation without one would collide them and give two cells
#: the same reading.
_SEPARATOR = "\x1f"

_DIGEST_BYTES = 16

#: The mantissa of a float64. Taking the top 53 bits of the digest gives every
#: representable value in [0, 1) equal weight and no more precision than the
#: type can carry.
_UNIT_BITS = 53


def _digest(seed: int, keys: tuple[object, ...]) -> int:
    material = _SEPARATOR.join([str(seed), *(str(key) for key in keys)])
    return int.from_bytes(
        hashlib.blake2b(material.encode("utf-8"), digest_size=_DIGEST_BYTES).digest(),
        "big",
    )


def derive_unit(seed: int, *keys: object) -> float:
    """A float in `[0, 1)`, determined entirely by the seed and the keys.

    The same seed and keys give the same value on any machine, in any order,
    in any process. Different keys under one seed are independent for every
    purpose this project has -- one cell's noise says nothing about the next
    cell's.
    """
    return (_digest(seed, keys) >> (_DIGEST_BYTES * 8 - _UNIT_BITS)) / (1 << _UNIT_BITS)


def derive_gaussian(seed: int, *keys: object) -> float:
    """A standard normal deviate, determined by the seed and the keys.

    Box-Muller over two derived uniforms rather than `random.gauss`, so the
    transform is visible and owned here rather than being whatever the standard
    library's implementation happens to be in a given version.

    `1.0 - u` moves the first uniform from `[0, 1)` to `(0, 1]`: zero is the one
    input the logarithm cannot take, and it is reachable with probability
    2^-53 -- rare enough to survive every test and land in a campaign.
    """
    first = 1.0 - derive_unit(seed, *keys, "gauss-a")
    second = derive_unit(seed, *keys, "gauss-b")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def new_seed() -> int:
    """Draw a seed for a run that was not given one.

    The caller must record what comes back. A run whose seed was generated and
    then not written down can never be repeated, which is `scn-001`'s third
    failure case and the reason `RunSpec.create` is the only caller.
    """
    return secrets.randbelow(SEED_MAX + 1)
