"""Edge-side mirror of the §6 wire contracts (kept in sync with the cloud's
app/contracts.py). Plain dicts — Home Assistant core ships no pydantic — but the
shapes and `schema_version` are identical and must be versioned in lock-step.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .const import SCHEMA_VERSION


def build_candidate_signal(
    *,
    signal_type: str,
    entities: list[str],
    evidence: dict,
    priority: str = "normal",
    area_id: str | None = None,
    detected_at: datetime | None = None,
    signal_id: str | None = None,
) -> dict:
    """Build one §6.1 candidate signal. `signal_id` is the idempotency key."""
    return {
        "schema_version": SCHEMA_VERSION,
        "signal_id": signal_id or str(uuid.uuid4()),
        "type": signal_type,
        "priority": priority,
        "detected_at": (detected_at or datetime.now(UTC)).isoformat(),
        "entities": entities,
        "evidence": evidence,
        "area_id": area_id,
    }


def build_upload_request(signals: list[dict]) -> dict:
    """Build a §6 SignalUploadRequest body."""
    return {"schema_version": SCHEMA_VERSION, "signals": signals}
