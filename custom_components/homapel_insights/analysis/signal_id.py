"""Deterministic signal ids for idempotent uploads (HA-free).

Re-detecting the same pattern within the same period yields the SAME signal_id,
so the cloud's upsert-on-signal_id dedupes it instead of piling up duplicate
rows. A new `period` (e.g. ISO week) lets a genuinely recurring pattern be
re-surfaced later.
"""

from __future__ import annotations

import uuid

# Fixed namespace for Laris insights signal ids (random, stable constant).
_NAMESPACE = uuid.UUID("6f9b1d2c-7a3e-4c1b-9f0a-2d4e6c8a1b35")


def deterministic_signal_id(
    unit_key: str, signal_type: str, entities: list[str], period: str
) -> str:
    key = f"{unit_key}|{signal_type}|{','.join(sorted(entities))}|{period}"
    return str(uuid.uuid5(_NAMESPACE, key))
