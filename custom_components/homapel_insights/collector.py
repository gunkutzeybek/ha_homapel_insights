"""Periodic recorder-history collection (HA-coupled).

Reads significant state history for the analyzed domains and reconstructs
`StateSpan`s, then hands them to the pure rollup. Also builds two context
streams the analyzers consume:

* an occupancy timeline (from `person`/`device_tracker` history) → each on-event
  is tagged `away` when the home was empty for the majority of its span;
* per-entity energy totals (from sibling kWh sensors on the same device).

Periodic-only for MVP (the plan's recommendation); live streaming is deferred to
a later safety allowlist.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .analysis.models import EntityWindow
from .analysis.occupancy import OccupancyTimeline, build_occupancy
from .analysis.rollup import StateSpan, build_windows

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

# Domains the analyzers care about. Energy/power live in `sensor` and are pulled
# separately as a context stream (see _collect_energy).
ANALYZED_DOMAINS = {"light", "switch", "fan", "climate", "cover", "media_player"}

# Domains that signal "someone is home".
PRESENCE_DOMAINS = {"person", "device_tracker"}

# Recorder state that means a tracker is at home.
_PRESENT_STATE = "home"

# Energy sensor units we know how to total (cumulative meters).
_ENERGY_UNITS = {"kWh": 1.0, "Wh": 0.001}


def _entities_in_domains(hass: HomeAssistant, domains: set[str]) -> list[str]:
    return [
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.split(".", 1)[0] in domains
    ]


def _area_map(hass: HomeAssistant, entity_ids: list[str]) -> dict[str, str]:
    registry = er.async_get(hass)
    out: dict[str, str] = {}
    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if entry and entry.area_id:
            out[entity_id] = entry.area_id
    return out


def _states_to_spans(entity_id: str, states: list[State], end_ts) -> list[StateSpan]:  # noqa: ANN001
    spans: list[StateSpan] = []
    for i, st in enumerate(states):
        start = getattr(st, "last_changed", None)
        if start is None:
            continue
        nxt = states[i + 1].last_changed if i + 1 < len(states) else end_ts
        context = getattr(st, "context", None)
        manual = bool(context and getattr(context, "user_id", None))
        spans.append(
            StateSpan(entity_id=entity_id, state=st.state, start=start, end=nxt, manual=manual)
        )
    return spans


def _present_intervals(states: list[State], end_ts) -> list[tuple]:  # noqa: ANN001
    """Intervals during which a single tracker reported 'home'."""
    intervals: list[tuple] = []
    for i, st in enumerate(states):
        start = getattr(st, "last_changed", None)
        if start is None:
            continue
        nxt = states[i + 1].last_changed if i + 1 < len(states) else end_ts
        if str(st.state).lower() == _PRESENT_STATE:
            intervals.append((start, nxt))
    return intervals


def _build_occupancy(
    history: dict, presence_ids: list[str], end  # noqa: ANN001
) -> OccupancyTimeline:
    if not presence_ids:
        return build_occupancy([], has_data=False)
    intervals: list[tuple] = []
    seen_data = False
    for entity_id in presence_ids:
        states = history.get(entity_id, [])
        if states:
            seen_data = True
        intervals.extend(_present_intervals(states, end))
    return build_occupancy(intervals, has_data=seen_data)


def _energy_sensor_ids(hass: HomeAssistant) -> dict[str, float]:
    """Map kWh-capable energy sensor entity_id → unit scale factor (→ kWh)."""
    out: dict[str, float] = {}
    for state in hass.states.async_all("sensor"):
        unit = state.attributes.get("unit_of_measurement")
        if unit in _ENERGY_UNITS:
            out[state.entity_id] = _ENERGY_UNITS[unit]
    return out


def _device_energy_map(
    hass: HomeAssistant, controllable_ids: list[str], energy_scale: dict[str, float]
) -> dict[str, list[str]]:
    """Map each controllable entity → energy sensors sharing its device."""
    registry = er.async_get(hass)
    energy_by_device: dict[str, list[str]] = {}
    for sensor_id in energy_scale:
        entry = registry.async_get(sensor_id)
        if entry and entry.device_id:
            energy_by_device.setdefault(entry.device_id, []).append(sensor_id)
    out: dict[str, list[str]] = {}
    for entity_id in controllable_ids:
        entry = registry.async_get(entity_id)
        if entry and entry.device_id and entry.device_id in energy_by_device:
            out[entity_id] = energy_by_device[entry.device_id]
    return out


def _total_kwh(states: list[State], scale: float) -> float:
    """Sum positive deltas of a cumulative meter (resets count as 0)."""
    total = 0.0
    prev: float | None = None
    for st in states:
        try:
            value = float(st.state)
        except (TypeError, ValueError):
            continue
        if prev is not None and value >= prev:
            total += value - prev
        prev = value
    return total * scale


def _collect_energy(
    history: dict,
    energy_map: dict[str, list[str]],
    energy_scale: dict[str, float],
) -> dict[str, float]:
    per_entity: dict[str, float] = {}
    for entity_id, sensor_ids in energy_map.items():
        total = sum(
            _total_kwh(history.get(sid, []), energy_scale[sid]) for sid in sensor_ids
        )
        if total > 0:
            per_entity[entity_id] = total
    return per_entity


def _apply_context(
    windows: list[EntityWindow],
    occupancy: OccupancyTimeline,
    energy_by_entity: dict[str, float],
) -> None:
    """Tag on-events with `away` and windows with `energy_kwh` (in place)."""
    for w in windows:
        if (kwh := energy_by_entity.get(w.entity_id)) is not None:
            w.energy_kwh = kwh
        for ev in w.on_events:
            ev.away = occupancy.is_away(
                ev.start, ev.start + timedelta(seconds=ev.duration_s)
            )


async def collect_windows(hass: HomeAssistant, lookback: timedelta) -> list[EntityWindow]:
    # Loop-side HA lookups (state machine + entity registry).
    entity_ids = _entities_in_domains(hass, ANALYZED_DOMAINS)
    if not entity_ids:
        return []
    area_map = _area_map(hass, entity_ids)
    presence_ids = _entities_in_domains(hass, PRESENCE_DOMAINS)
    energy_scale = _energy_sensor_ids(hass)
    energy_map = _device_energy_map(hass, entity_ids, energy_scale)

    end = dt_util.utcnow()
    start = end - lookback
    history_ids = sorted(
        set(entity_ids)
        | set(presence_ids)
        | {sid for ids in energy_map.values() for sid in ids}
    )

    # Single batched recorder read on the recorder executor.
    history = await get_instance(hass).async_add_executor_job(
        get_significant_states, hass, start, end, history_ids
    )

    # Pure processing back on the loop.
    spans: list[StateSpan] = []
    for entity_id in entity_ids:
        spans.extend(_states_to_spans(entity_id, history.get(entity_id, []), end))
    windows = build_windows(spans, area_map)

    occupancy = _build_occupancy(history, presence_ids, end)
    energy_by_entity = _collect_energy(history, energy_map, energy_scale)
    _apply_context(windows, occupancy, energy_by_entity)
    return windows
