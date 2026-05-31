"""Laris Insights — edge integration.

Periodic loop (Phase 1): read recorder history → deterministic analyzers →
privacy minimization → upload candidate signals → deliver any returned
suggestions as notifications. The LLM lives only in the cloud; the edge ships
aggregated signals, never raw telemetry.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .analysis.energy_waste import EnergyWasteAnalyzer
from .analysis.left_on import LeftOnAnalyzer
from .analysis.models import Analyzer, CandidateSignalData
from .analysis.on_while_away import OnWhileAwayAnalyzer
from .analysis.privacy import apply_privacy
from .analysis.recurring_manual import RecurringManualAnalyzer
from .analysis.signal_id import deterministic_signal_id
from .collector import collect_windows
from .const import (
    CONF_API_KEY,
    CONF_CLOUD_BASE_URL,
    CONF_OPT_IN,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    SERVICE_UPLOAD_TEST_SIGNAL,
)
from .contracts import build_candidate_signal
from .delivery import deliver_suggestions
from .storage import InsightsStore
from .uploader import InsightsUploader

if TYPE_CHECKING:
    from .analysis.models import EntityWindow

_LOGGER = logging.getLogger(__name__)

# How far back each tick reads history. Wider than the poll interval so a missed
# tick doesn't lose coverage; the cloud dedupes via deterministic signal ids.
_HISTORY_LOOKBACK = timedelta(days=14)


def _build_analyzers() -> list[Analyzer]:
    return [
        LeftOnAnalyzer(),
        RecurringManualAnalyzer(),
        OnWhileAwayAnalyzer(),
        EnergyWasteAnalyzer(),
    ]


def _run_analyzers(windows: list[EntityWindow]) -> list[CandidateSignalData]:
    signals: list[CandidateSignalData] = []
    for analyzer in _build_analyzers():
        signals.extend(analyzer.analyze(windows))
    return signals


def _to_wire_signals(unit_key: str, signals: list[CandidateSignalData]) -> list[dict]:
    period = _current_period()
    return [
        build_candidate_signal(
            signal_type=s.type,
            entities=s.entities,
            evidence=s.evidence,
            priority=s.priority,
            area_id=s.area_id,
            signal_id=deterministic_signal_id(unit_key, s.type, s.entities, period),
        )
        for s in signals
    ]


def _current_period() -> str:
    iso = dt_util.utcnow().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not entry.data.get(CONF_OPT_IN, False):
        _LOGGER.info("homapel_insights not opted in; skipping setup")
        return False

    session = async_get_clientsession(hass)
    uploader = InsightsUploader(
        session=session,
        base_url=entry.data[CONF_CLOUD_BASE_URL],
        api_key=entry.data[CONF_API_KEY],
    )
    store = InsightsStore(hass, entry.entry_id)
    await store.load()
    # api_key is the unit identity; use a short prefix as the dedupe key salt.
    unit_key = entry.data[CONF_API_KEY][:12]

    async def _poll(_now=None) -> None:
        # 1. Flush any queued feedback first (pull model — same channel).
        for fb in store.drain_feedback():
            await uploader.send_feedback(fb["suggestion_id"], fb["action"])

        # 2. Collect → analyze → minimize → upload.
        try:
            windows = await collect_windows(hass, _HISTORY_LOOKBACK)
            candidates = apply_privacy(_run_analyzers(windows))
            wire_signals = _to_wire_signals(unit_key, candidates)
        except Exception:  # never let analysis errors kill the poll loop
            _LOGGER.exception("insights analysis failed")
            wire_signals = []

        suggestions = await uploader.upload(signals=wire_signals)
        if suggestions:
            await deliver_suggestions(hass, suggestions)

        store.last_run = dt_util.utcnow().isoformat()
        await store.save()

    async def _upload_test_signal(call: ServiceCall) -> None:
        signal = build_candidate_signal(
            signal_type=call.data.get("type", "waste.left_on"),
            entities=call.data.get("entities", ["light.hallway"]),
            evidence=call.data.get("evidence", {"hours_on": 9}),
            area_id=call.data.get("area_id"),
        )
        suggestions = await uploader.upload(signals=[signal])
        await deliver_suggestions(hass, suggestions)

    cancel = async_track_time_interval(hass, _poll, DEFAULT_POLL_INTERVAL)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "uploader": uploader,
        "store": store,
        "cancel_poll": cancel,
    }
    hass.services.async_register(DOMAIN, SERVICE_UPLOAD_TEST_SIGNAL, _upload_test_signal)
    _LOGGER.info("homapel_insights set up for entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and (cancel := data.get("cancel_poll")):
        cancel()
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_UPLOAD_TEST_SIGNAL)
    return True
