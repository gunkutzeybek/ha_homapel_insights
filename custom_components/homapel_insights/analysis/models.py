"""Shared, HA-free data structures for the collection/aggregation layer.

These are the edge's whole output surface: the collector builds EntityWindows
from recorder history, and `analysis.observation` projects them straight onto the
§6.1 wire shape. There is no edge-side decision layer — the cloud LLM decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OnEvent:
    """A single 'on' interval for an entity.

    `manual` marks user-initiated changes (vs automation-triggered) — the
    collector sets it from the recorder's stored context; defaults True until
    Phase 1.5 wires context parsing.

    `away` marks an interval where the home was unoccupied for the majority of
    its span (the collector sets it from the occupancy timeline); defaults False
    so analyzers never flag "away" without positive presence evidence.
    """

    start: datetime
    duration_s: float
    manual: bool = True
    away: bool = False


@dataclass
class EntityWindow:
    """All 'on' events for one entity over the rollup window.

    `energy_kwh` is the total energy this entity drew over the window, when a
    sibling energy sensor exists on the same device; None when unknown.
    """

    entity_id: str
    domain: str
    on_events: list[OnEvent] = field(default_factory=list)
    area_id: str | None = None
    energy_kwh: float | None = None
