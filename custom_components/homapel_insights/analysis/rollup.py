"""Turn raw state spans into per-entity rollup windows (HA-free).

A 'span' is a contiguous period an entity held a single state, as reconstructed
from recorder history: (entity_id, state, start, end). We fold the "on" spans
into `OnEvent`s per entity. The collector produces spans from HA; this stays
pure so it's unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import EntityWindow, OnEvent

# States that count as "on" for the domains we analyze.
_ON_STATES = {"on", "open", "playing", "home", "heat", "cool", "auto"}


@dataclass
class StateSpan:
    entity_id: str
    state: str
    start: datetime
    end: datetime
    manual: bool = True

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]

    @property
    def duration_s(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())


def is_on(state: str) -> bool:
    return state.lower() in _ON_STATES


def build_windows(
    spans: list[StateSpan], area_by_entity: dict[str, str] | None = None
) -> list[EntityWindow]:
    """Group "on" spans into one EntityWindow per entity."""
    area_by_entity = area_by_entity or {}
    windows: dict[str, EntityWindow] = {}
    for span in spans:
        if not is_on(span.state):
            continue
        window = windows.get(span.entity_id)
        if window is None:
            window = EntityWindow(
                entity_id=span.entity_id,
                domain=span.domain,
                area_id=area_by_entity.get(span.entity_id),
            )
            windows[span.entity_id] = window
        window.on_events.append(
            OnEvent(start=span.start, duration_s=span.duration_s, manual=span.manual)
        )
    return list(windows.values())
