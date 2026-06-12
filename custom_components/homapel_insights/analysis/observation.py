"""Project rollup EntityWindows into §6.1 ObservationWindow dicts (HA-free).

This is the edge's whole job now: a straight field mapping from the aggregated
EntityWindow to the wire shape — NO analysis, NO thresholds, NO verdicts. The
cloud LLM decides whether any observation warrants a suggestion. The edge is the
senses, not the brain.

The aggregation level (per-entity `on_events`, not raw recorder state logs) is
deliberate minimization — we ship activity windows, never telemetry.
"""

from __future__ import annotations

from .models import EntityWindow, OnEvent


def on_event_to_wire(event: OnEvent) -> dict:
    """One §6.1 on-event: {start, duration_s, manual, away}."""
    return {
        "start": event.start.isoformat(),
        "duration_s": event.duration_s,
        "manual": event.manual,
        "away": event.away,
    }


def to_observation(window: EntityWindow) -> dict:
    """One §6.1 ObservationWindow — a direct projection of an EntityWindow.

    No id and no timestamps: the cloud owns dedup, deriving its row key as
    uuid5(unit_id, entity_id) and UPSERTing ONE row per entity with the freshest
    rollup on every upload. So the edge just ships the current window per entity
    each tick; re-uploading the overlapping lookback self-dedupes cloud-side.
    """
    return {
        "entity_id": window.entity_id,
        "domain": window.domain,
        "area_id": window.area_id,
        "energy_kwh": window.energy_kwh,
        "on_events": [on_event_to_wire(e) for e in window.on_events],
    }
