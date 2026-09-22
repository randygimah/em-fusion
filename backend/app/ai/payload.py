"""What actually leaves the machine. Spec: ai-004.

The one definition of how an evidence bundle is serialised for a hosted
provider, and it lives here for a reason that is not tidiness.

**§4 of the phase 9 document measured the egress payload field by field.**
That measurement is what closed the Track 0 data-egress gate and what
NFR-405 rests on: no aircraft position reaches a bundle at all, and a track
citation carries a `dal-004` pseudonym and a timestamp. It was taken
against a payload dictionary **hand-written inside
`measurements/corpus/bundle_payload.py`**, and nothing in `app/` serialised
a bundle at all -- so unless the adapter shipped that exact dictionary, the
thing measured was not the thing that would be sent. Moving it here puts it
where lint, mypy and the coverage gate can see it, and the measurement
re-runs against this function rather than beside it.

**Two fields are excluded, and both are our bookkeeping rather than
evidence.** A bundle's `scenario_run_id` is a database key, and an item's
`observation_ids` are the row ids `evb-002` resolved its citations to.
Neither is usable by a model, which cannot query the store, and both were
absent from the payload §4 measured -- so naming them keeps the shipped
serialiser and the figure of record describing the same thing. The
exclusions are frozen sets asserted by name in the suite, because an
exclusion set that can quietly grow is the same defect this module exists
to fix, one level up.

**`superseded` is sent**, labelled by the prompt as claims the system
rejected. It is what lets a model write an honest alternative rather than
inventing one, and it creates precisely the trap `ai-008` exists to catch:
a hypothesis citing a rejected claim as *support*. Sending it is also what
makes `ai-008`'s second failure case testable on real data rather than
only on constructed bundles.
"""

from __future__ import annotations

import json
from typing import Any

from app.detection.bundle import EvidenceBundle, EvidenceItem

#: Bundle fields deliberately not sent. See the module note.
BUNDLE_EXCLUDED = frozenset({"scenario_run_id"})

#: Evidence-item fields deliberately not sent.
ITEM_EXCLUDED = frozenset({"observation_ids"})


def _item(item: EvidenceItem) -> dict[str, Any]:
    return {
        "source": item.source,
        "finding": item.finding,
        "rule_id": item.rule_id,
        "finding_type": item.finding_type,
        "data_mode": item.data_mode.value,
        "grounding": item.grounding.value,
        "started_at": item.started_at.isoformat(),
        "ended_at": item.ended_at.isoformat(),
        "refs": [dict(ref) for ref in item.refs],
        "details": dict(item.details),
    }


def bundle_payload(bundle: EvidenceBundle) -> dict[str, Any]:
    """One bundle as the object a provider receives.

    Every value is already a JSON primitive -- times as ISO strings, enums
    as their values -- so no caller supplies an encoder. Two callers with
    two encoders are two payloads from one bundle, and the campaign's
    premise is that every arm saw the same input.
    """
    return {
        "anomaly_type": bundle.anomaly_type,
        "rule_id": bundle.rule_id,
        "subject": bundle.subject,
        "time_window": [t.isoformat() for t in bundle.time_window],
        "affected_area": {
            "lat": bundle.affected_area.lat,
            "lon": bundle.affected_area.lon,
        },
        "affected_channels": list(bundle.affected_channels),
        "evidence": [_item(item) for item in bundle.evidence],
        "known_uncertainties": [
            {
                "kind": u.kind.value,
                "subject": u.subject,
                "statement": u.statement,
            }
            for u in bundle.known_uncertainties
        ],
        "superseded": [
            {
                "rule_id": c.rule_id,
                "anomaly_type": c.anomaly_type,
                "claimed_by": c.claimed_by,
                "reason": c.reason,
            }
            for c in bundle.superseded
        ],
    }


def payload_json(bundle: EvidenceBundle) -> str:
    """The payload as the exact bytes sent.

    `sort_keys` is not used: the dictionary above is written in a fixed
    order and Python preserves it, so the bytes are stable without
    reordering the document a person reads.
    """
    return json.dumps(bundle_payload(bundle), ensure_ascii=False)


__all__ = ["BUNDLE_EXCLUDED", "ITEM_EXCLUDED", "bundle_payload", "payload_json"]
