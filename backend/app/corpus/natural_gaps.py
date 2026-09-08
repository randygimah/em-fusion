"""The injection-exclusion list. Spec: adp-008.

Scenario type 4 stages a coverage gap by suppressing an aircraft's reports for
a window. About 1% of the tracks in the corpus already carry a gap of their
own, and seven of those ten sit in the 100-300 s band a plausible injection
occupies, so injecting onto one of them produces a run whose ground truth and
whose data disagree about what happened. This module names those tracks so the
generator can refuse them.

**Why `coverage.json` cannot serve.** It measures every interval between
consecutive positioned rows and reports the distribution -- a maximum, three
percentiles, a clean-cadence fraction. It keeps no identity, which is the one
thing needed here, and it applies neither of the two filters that separate a
coverage failure from an artefact of having drawn a box:

* **Interior.** An aircraft that flies out of the box and back in leaves an
  interval with nothing in it, and nothing went wrong. Only a gap bracketed by
  two rows comfortably inside the boundary is evidence about coverage. This is
  the same correction the bounding-box sweep needed, where the naive figure
  reported gaps of 3,140 s in a 3,600 s file.
* **Airborne.** An aircraft parked on a stand stops reporting because it has
  been switched off.

**Identities are pseudonyms, and the artefact is committed.** `icao24` is a
24-bit space, so a committed file of source identifiers would hand a reader the
mapping `dal-004` exists to prevent. The generator perturbs source records
before the DAL sees them, so it derives the pseudonym for each candidate track
and tests membership against this list rather than the reverse. The list is
therefore meaningful only against the seed whose fingerprint it records.

**Where the rules are uncertain, this over-reports.** A row whose ground flag
is missing is treated as airborne, so its gap is listed. Being on the list
costs one candidate injection site out of hundreds; being absent from it when
the track carries a real dropout costs the false-positive rate for an entire
scenario type. The asymmetry is not close, and the choice is recorded rather
than left to whichever branch was written first.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from app.corpus.extract import BoundingBox
from app.dal.pseudonymise import Pseudonymiser

#: Twice the 10 s reporting cadence: one missed beat is the smallest thing that
#: can be called a gap rather than jitter. The shortest gap in the chosen box
#: measures exactly this, so a higher floor would drop a real one.
DEFAULT_MIN_GAP_S = 20

#: How far inside the boundary a row must sit for the gap it brackets to count.
#: A quarter degree is roughly 28 km north-south, which an airliner covers in
#: about two minutes -- so a gap shorter than that cannot be an undetected exit
#: and re-entry, and a longer one is caught by the margin at whichever end the
#: aircraft crossed.
DEFAULT_INTERIOR_MARGIN_DEG = 0.25

#: Ground flag values that mean the aircraft is not flying. Compared
#: case-insensitively against the string form, because the same field arrives
#: as the text `"True"` from the CSV reader and as a real boolean from the
#: Parquet extract, and a check that handles only one silently accepts the
#: other as airborne.
_ON_GROUND = frozenset({"true", "1"})


@dataclass(frozen=True)
class NaturalGap:
    """One aircraft's interior airborne gap, by pseudonym."""

    aircraft_id: str
    start: int
    end: int
    duration_s: int


def _coordinate(value: Any) -> float | None:
    """A coordinate, or None when the row carries no position.

    The 500 retained null-position rows exist to give the quarantine path real
    input; treating one as a gap boundary would invent a gap out of a retention
    decision rather than measure one.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _airborne(value: Any) -> bool:
    """Whether the aircraft was flying. Missing means yes -- see the module
    docstring on which direction to be wrong in."""
    if value is None or value == "":
        return True
    return str(value).strip().lower() not in _ON_GROUND


def _interior(box: BoundingBox, lat: float, lon: float, margin_deg: float) -> bool:
    """Whether a point sits inside the box by at least the margin on all sides."""
    return (
        box.lat_min + margin_deg <= lat <= box.lat_max - margin_deg
        and box.lon_min + margin_deg <= lon <= box.lon_max - margin_deg
    )


def find_natural_gaps(
    rows: Iterable[Mapping[str, Any]],
    *,
    box: BoundingBox,
    min_gap_s: int = DEFAULT_MIN_GAP_S,
    margin_deg: float = DEFAULT_INTERIOR_MARGIN_DEG,
    pseudonymiser: Pseudonymiser,
) -> list[NaturalGap]:
    """Every interior airborne gap in the rows, as pseudonymous records.

    Rows are grouped per aircraft and sorted by time before intervals are
    measured. The extract is written in ascending time order, so the sort
    changes nothing today -- and an out-of-order pair would produce a negative
    interval, which falls below any minimum and hides a real gap rather than
    reporting a wrong one. Nothing would notice, which is why it is not left to
    trust.
    """
    positions: dict[str, list[tuple[int, float, float, bool]]] = defaultdict(list)

    for row in rows:
        lat = _coordinate(row.get("lat"))
        lon = _coordinate(row.get("lon"))
        if lat is None or lon is None:
            continue
        identifier = row.get("icao24")
        if not identifier:
            continue
        positions[str(identifier)].append(
            (
                int(float(row["time"])),
                lat,
                lon,
                _airborne(row.get("onground")),
            )
        )

    found: list[NaturalGap] = []
    for identifier, samples in positions.items():
        samples.sort(key=lambda sample: sample[0])
        pseudonym = pseudonymiser.aircraft(identifier)
        if pseudonym is None:  # pragma: no cover -- filtered above
            continue

        for earlier, later in zip(samples, samples[1:]):
            duration = later[0] - earlier[0]
            if duration < min_gap_s:
                continue
            if not (earlier[3] and later[3]):
                continue
            if not (
                _interior(box, earlier[1], earlier[2], margin_deg)
                and _interior(box, later[1], later[2], margin_deg)
            ):
                continue
            found.append(
                NaturalGap(
                    aircraft_id=pseudonym,
                    start=earlier[0],
                    end=later[0],
                    duration_s=duration,
                )
            )

    # Sorted rather than left in dictionary order: the artefact is committed,
    # and an unstable order produces a diff on every rebuild that buries the one
    # change worth seeing.
    found.sort(key=lambda gap: (gap.aircraft_id, gap.start))
    return found


def build_natural_gaps_report(
    gaps: Iterable[NaturalGap],
    *,
    box: BoundingBox,
    min_gap_s: int = DEFAULT_MIN_GAP_S,
    margin_deg: float = DEFAULT_INTERIOR_MARGIN_DEG,
    seed_fingerprint: str,
) -> dict[str, Any]:
    """The committed artefact: the gaps, and what produced them.

    The parameters are recorded beside the result because a list of identifiers
    is uninterpretable a year later without them -- and because the identifiers
    are pseudonyms, which mean nothing at all against a different seed. The
    fingerprint is how a reader tells whether this list describes the extract
    they are holding.
    """
    listed = list(gaps)
    return {
        "min_gap_s": min_gap_s,
        "interior_margin_deg": margin_deg,
        "bounding_box": asdict(box),
        "pseudonym_seed_sha256": seed_fingerprint,
        "aircraft": len({gap.aircraft_id for gap in listed}),
        "gaps": [asdict(gap) for gap in listed],
    }
