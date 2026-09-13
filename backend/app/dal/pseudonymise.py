"""Aircraft identifier pseudonymisation. Spec: dal-004.

OpenSky DLA section 3(i) obliges the licensee to de-identify aircraft
identifiers for any publication or other disclosure, and section 3(iii)
forbids making the data available outside the licensee's institute. The
figures in the write-up, the evidence bundles sent to a hosted provider, and
any captured screen are all disclosure. The real values stay in the local
extract, which the licence permits; nothing past this module sees them.

The substitution happens here rather than in the OpenSky adapter for the
reason `dal-003` gives for provenance: an obligation that holds across every
source is discharged once, where a new adapter inherits it without its author
having to know the licence exists. `IDENTIFIER_RULES` is the registration
point -- a source with no identifiers passes through untouched.

**The seed is not in the repository, and must never be.** `icao24` is a
24-bit space of about 16.7 million values, so anyone holding the seed and
this file reconstructs the whole mapping by exhaustive search in seconds. A
committed seed is a readable reverse mapping, which is the thing being
prevented. It is read from the environment; the manifest records
`fingerprint()` instead, which keeps a seed change a detectable corpus-level
event without publishing the value.

The mapping is a property of the **corpus**, not of a run. The extract is one
replayed hour and the same airframes recur in every run of a batch, so
deriving from the scenario seed would give one aircraft a different label in
each of twenty-five runs and make the batch non-comparable.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.dal.models import ObservationType

#: Environment variable holding the seed. Documented in `.env.example`;
#: never given a default, because a default seed is a committed seed.
SEED_ENV_VAR = "PSEUDONYM_SEED"

#: Hex characters kept from the digest: 48 bits. Over the corpus's 1,445
#: distinct addresses the collision probability is around 4e-9, and a
#: collision merges two airframes into one track silently -- so the margin is
#: deliberate rather than incidental.
PSEUDONYM_LENGTH = 12


class IdentifierError(ValueError):
    """A source record's identifiers cannot be canonicalised."""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


@dataclass(frozen=True)
class IdentifierRule:
    """One source field to replace, and what it becomes."""

    source_field: str
    canonical_field: str
    prefix: str
    required: bool


#: Which fields each observation type carries. Adding a source with its own
#: identifiers means adding an entry here and nothing else.
IDENTIFIER_RULES: dict[ObservationType, tuple[IdentifierRule, ...]] = {
    ObservationType.TRACK: (
        IdentifierRule("icao24", "aircraft_id", "AC", required=True),
        IdentifierRule("callsign", "flight_id", "FL", required=False),
    ),
    ObservationType.RF: (),
}


class Pseudonymiser(BaseModel):
    """A seeded, deterministic mapping from source identifier to pseudonym.

    Holds no state beyond the seed. A cache keyed by source identifier would
    be exactly the reverse mapping the spec forbids, so the derivation is a
    pure function of the seed and the input every time.
    """

    model_config = ConfigDict(frozen=True)

    seed: str = Field(repr=False)

    @field_validator("seed")
    @classmethod
    def _seed_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("the pseudonymisation seed must not be blank")
        return value

    @classmethod
    def from_environment(cls) -> Pseudonymiser:
        """Read the seed from the environment, or fail loudly."""
        seed = os.environ.get(SEED_ENV_VAR, "")
        if not seed.strip():
            raise RuntimeError(
                f"{SEED_ENV_VAR} is not set. The pseudonymisation seed is fixed "
                f"project configuration held outside the repository; see "
                f"backend/.env.example. There is deliberately no default."
            )
        return cls(seed=seed)

    def fingerprint(self) -> str:
        """A commitment to the seed, safe to record in the committed manifest.

        Identifies *which* seed built a corpus without disclosing it, so
        changing the seed stays a recorded event rather than a silent one.
        """
        return hashlib.sha256(self.seed.encode()).hexdigest()

    def derive(self, namespace: str, prefix: str, value: Any) -> str | None:
        """Pseudonymise one value, or return None if there is nothing to map.

        The namespace is mixed into the message so the identifier spaces stay
        independent: an `icao24` and a callsign that happen to share text must
        not land on the same pseudonym.

        Whitespace and case are normalised first. OpenSky pads callsigns to a
        fixed width, and `DLH8AT ` against `DLH8AT  ` would otherwise be two
        aircraft as far as every continuity rule is concerned.
        """
        if value is None:
            return None
        text = str(value).strip().casefold()
        if not text:
            return None
        digest = hmac.new(
            self.seed.encode(), f"{namespace}:{text}".encode(), hashlib.sha256
        ).hexdigest()
        return f"{prefix}-{digest[:PSEUDONYM_LENGTH]}"

    def aircraft(self, value: Any) -> str | None:
        return self.derive("icao24", "AC", value)

    def flight(self, value: Any) -> str | None:
        return self.derive("callsign", "FL", value)


def substitute(
    observation_type: ObservationType,
    payload: Mapping[str, Any],
    pseudonymiser: Pseudonymiser,
) -> dict[str, Any]:
    """Replace a payload's source identifiers with pseudonyms.

    The source values are removed rather than kept alongside: retaining one
    satisfies the letter of the mapping while leaving the real value a single
    query away.
    """
    canonical = dict(payload)

    for rule in IDENTIFIER_RULES.get(observation_type, ()):
        if rule.canonical_field in canonical:
            raise IdentifierError(
                f"payload.{rule.canonical_field}",
                "pseudonyms are derived by the DAL, not supplied by an adapter",
            )

        pseudonym = pseudonymiser.derive(
            rule.source_field, rule.prefix, canonical.pop(rule.source_field, None)
        )
        if pseudonym is None and rule.required:
            raise IdentifierError(
                f"payload.{rule.source_field}",
                f"{rule.source_field} is required and was not supplied",
            )
        canonical[rule.canonical_field] = pseudonym

    return canonical


def load_seed_environment(env_file: Path | None) -> None:
    """Make the seed readable, whether it comes from the environment or a file.

    Compose passes the seed through from the host, so an **unset host variable
    arrives inside a container as an empty string rather than as absent** — and
    `load_dotenv(override=False)` treats present-but-empty as present, which
    would let nothing shadow a perfectly good `.env`. An empty seed is not a
    seed, which `Pseudonymiser.from_environment` already says one layer down,
    so it is cleared before the file is read.

    A seed genuinely set in the environment still wins: `override=False` leaves
    it alone, and only an empty one is cleared.

    **This exists as one function because it had become three sites.** Both
    command-line entrypoints carried their own copy with their own comment, and
    the batch launcher — added later, by a route rather than a command — did
    not, so every batch started from the screen died on a missing seed while
    the screen reported it accepted. A remedy copied twice is a remedy the
    third caller will not know about.
    """
    if not os.environ.get(SEED_ENV_VAR, "").strip():
        os.environ.pop(SEED_ENV_VAR, None)
    if env_file is not None and Path(env_file).is_file():
        load_dotenv(env_file, override=False)
