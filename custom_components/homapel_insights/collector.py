"""Periodic recorder-history collection (HA-coupled).

Reads significant state history for the analyzed domains and reconstructs
`StateSpan`s, then hands them to the pure rollup. Periodic-only for MVP (the
plan's recommendation); live streaming is deferred to a later safety allowlist.
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
from .analysis.rollup import StateSpan, build_windows

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

# Domains the MVP analyzers care about. Energy/climate domains arrive in Phase 4.
ANALYZED_DOMAINS = {"light", "switch", "fan"}


def _candidate_entities(hass: HomeAssistant) -> list[str]:
    return [
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.split(".", 1)[0] in ANALYZED_DOMAINS
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


async def collect_windows(hass: HomeAssistant, lookback: timedelta) -> list[EntityWindow]:
    entity_ids = _candidate_entities(hass)
    if not entity_ids:
        return []

    end = dt_util.utcnow()
    start = end - lookback
    states_by_entity = await get_instance(hass).async_add_executor_job(
        get_significant_states, hass, start, end, entity_ids
    )

    spans: list[StateSpan] = []
    for entity_id, states in states_by_entity.items():
        spans.extend(_states_to_spans(entity_id, states, end))

    return build_windows(spans, _area_map(hass, entity_ids))
