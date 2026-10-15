"""The receiver health feed's numbers. Spec: adp-003.

The third source, built to measure what adding a source costs (RQ1): each
layout receiver reports its temperature, supply voltage and uptime once a
minute of simulated time. Nothing reads it.

**Blind to the incident by its signature.** It takes the seed, start, duration
and layout, never a `RunSpec` or an incident, so it cannot know what a run
stages: a self-report that moved with the incident would hand any reader the
answer key (`api-009`).

Every number comes from `seeding.py`, keyed on the seed, the receiver and the
minute, as `scn-001`'s grid is.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.dal.models import ObservationType, SourceType
from app.scenario.layout import RfLayout
from app.scenario.seeding import derive_gaussian, derive_unit

SOURCE_ID = "synthetic-health"

#: One report per receiver per minute of simulated time.
INTERVAL_SECONDS = 60

_SECONDS_PER_DAY = 86_400


def emit_health(
    layout: RfLayout, seed: int, start: datetime, duration_seconds: int
) -> tuple[dict[str, Any], ...]:
    """The whole feed, as source records, ordered by time then receiver.

    Half-open on the duration, like `scn-001`'s ticks. Each receiver has been
    up for a seeded whole number of seconds under a day at the start, and its
    uptime then grows with simulated time.
    """
    sensors = sorted(layout.sensors, key=lambda site: site.sensor_id)
    steps = -(-duration_seconds // INTERVAL_SECONDS)
    return tuple(
        {
            "source_id": SOURCE_ID,
            "source_type": SourceType.SYNTHETIC_HEALTH,
            "observation_type": ObservationType.RECEIVER_HEALTH,
            "timestamp": start + timedelta(seconds=step * INTERVAL_SECONDS),
            "location": {"lat": site.lat, "lon": site.lon},
            "payload": {
                "sensor_id": site.sensor_id,
                "temperature_c": 30.0
                + 10.0 * derive_unit(seed, "health-temperature", site.sensor_id)
                + 0.5
                * derive_gaussian(seed, "health-temperature", site.sensor_id, step),
                "supply_voltage_v": 12.0
                + 0.05 * derive_gaussian(seed, "health-voltage", site.sensor_id, step),
                "uptime_s": float(
                    int(
                        _SECONDS_PER_DAY
                        * derive_unit(seed, "health-boot", site.sensor_id)
                    )
                    + step * INTERVAL_SECONDS
                ),
            },
        }
        for step in range(steps)
        for site in sensors
    )
