"""Privacy minimization (HA-free).

Aggregate, don't ship raw logs. Two guarantees enforced before anything leaves
the home, operating on §6.1 ObservationWindow dicts:

* consent allow-list — drop observations for any entity the user hasn't opted in
  on (whole-home opt-in is the MVP; a per-entity set is Phase 2);
* coarse time — floor each on-event's precise `start` to the top of the hour, so
  the cloud sees hour-resolution timing, never minute-precise activity.

The on_events aggregation level itself (vs raw state logs) is the primary
minimization and is preserved upstream; this layer is the consent + precision gate.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime


def _coarsen_start(iso_start: str) -> str:
    """Floor an ISO-8601 timestamp to the top of its hour (drop min/sec/usec)."""
    try:
        dt = datetime.fromisoformat(iso_start)
    except ValueError:
        return iso_start
    return dt.replace(minute=0, second=0, microsecond=0).isoformat()


def _minimize_event(event: dict) -> dict:
    out = dict(event)
    start = out.get("start")
    if isinstance(start, str):
        out["start"] = _coarsen_start(start)
    return out


def apply_privacy(
    observations: list[dict],
    allowed_entities: Collection[str] | None = None,
) -> list[dict]:
    """Enforce consent + coarsen on-event timing on ObservationWindow dicts.

    `allowed_entities=None` means whole-home opt-in (everything allowed) — the
    MVP consent model. A set restricts output to consented entities (Phase 2);
    a non-consented entity's observation is dropped entirely.
    """
    out: list[dict] = []
    for obs in observations:
        if allowed_entities is not None and obs.get("entity_id") not in allowed_entities:
            continue
        minimized = dict(obs)
        minimized["on_events"] = [_minimize_event(e) for e in obs.get("on_events", [])]
        out.append(minimized)
    return out
