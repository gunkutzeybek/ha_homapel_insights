"""Laris Insights — edge integration (Phase 0 skeleton).

Phase 0 proves the end-to-end loop: a hand-crafted signal is uploaded to the
cloud, the response's pending suggestions are delivered as HA notifications.
Phase 1 adds the recorder collector, rollup, and the deterministic analyzers
(`left_on`, `recurring_manual`).
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

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
from .uploader import InsightsUploader

_LOGGER = logging.getLogger(__name__)


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

    async def _poll(_now=None) -> None:
        # Phase 0: no analyzers yet → upload an empty batch to pull pending
        # suggestions. Phase 1 passes the analyzers' candidate signals here.
        suggestions = await uploader.upload(signals=[])
        if suggestions:
            await deliver_suggestions(hass, suggestions)

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
