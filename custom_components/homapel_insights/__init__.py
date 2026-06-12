"""Laris Insights — edge integration.

Periodic loop: read recorder history → roll up into per-entity EntityWindows →
privacy minimization → upload aggregated observations → deliver any returned
suggestions as notifications. The edge is the senses, not the brain: it ships
aggregated observations, never raw telemetry and never edge-side verdicts. The
cloud LLM does all the deciding.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .analysis.privacy import apply_privacy
from .collector import collect_windows
from .const import (
    ACTION_PREFIX,
    ACTION_SEPARATOR,
    BTN_ACCEPT,
    BTN_REJECT,
    CONF_API_KEY,
    CONF_CLOUD_BASE_URL,
    CONF_OPT_IN,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    FEEDBACK_ACCEPTED,
    FEEDBACK_REJECTED,
    SERVICE_UPLOAD_TEST_SIGNAL,
)
from .contracts import build_observation_upload_request, build_observation_window
from .delivery import deliver_suggestions
from .executor import execute_accepted_action
from .storage import InsightsStore
from .uploader import InsightsUploader

_LOGGER = logging.getLogger(__name__)

# How far back each tick reads history. Wider than the poll interval so a missed
# tick doesn't lose coverage; the cloud upserts one row per entity, so the
# overlapping re-uploads self-dedupe.
_HISTORY_LOOKBACK = timedelta(days=14)


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

    def _to_observations(result) -> list[dict]:  # noqa: ANN001 — CollectionResult
        observations = [build_observation_window(w) for w in result.windows]
        return apply_privacy(observations)

    async def _poll(_now=None) -> None:
        # 1. Flush any queued feedback first (pull model — same channel).
        for fb in store.drain_feedback():
            await uploader.send_feedback(fb["suggestion_id"], fb["action"])

        # 2. Collect → roll up → minimize → upload aggregated observations.
        try:
            result = await collect_windows(hass, _HISTORY_LOOKBACK)
            request = build_observation_upload_request(
                window_start=result.window_start,
                window_end=result.window_end,
                had_presence_data=result.had_presence_data,
                observations=_to_observations(result),
            )
        except Exception:  # never let collection errors kill the poll loop
            _LOGGER.exception("insights collection failed")
            # Still POST an empty request so the pull half keeps delivering.
            now = dt_util.utcnow()
            request = build_observation_upload_request(
                window_start=now,
                window_end=now,
                had_presence_data=False,
                observations=[],
            )

        suggestions = await uploader.upload(request)
        if suggestions:
            await deliver_suggestions(hass, store, suggestions)

        store.last_run = dt_util.utcnow().isoformat()
        await store.save()

    async def _on_notification_action(event: Event) -> None:
        # A Companion-app Accept/Reject button was tapped. Decode it, run the
        # accepted action locally, and queue feedback for the next upload poll.
        action = event.data.get("action", "")
        if not action.startswith(ACTION_PREFIX):
            return  # not one of ours
        verb, _, suggestion_id = action[len(ACTION_PREFIX) :].partition(ACTION_SEPARATOR)
        if verb not in (BTN_ACCEPT, BTN_REJECT) or not suggestion_id:
            _LOGGER.warning("ignoring malformed insight action: %s", action)
            return

        stashed = store.pop_action(suggestion_id)
        if verb == BTN_ACCEPT and stashed:
            # Execute the side effect the cloud shipped (install automation /
            # run once). The cloud never touches the home — this is the edge's job.
            await execute_accepted_action(
                hass, suggestion_id, stashed["kind"], stashed.get("draft")
            )

        feedback = FEEDBACK_ACCEPTED if verb == BTN_ACCEPT else FEEDBACK_REJECTED
        store.queue_feedback(suggestion_id, feedback)
        await store.save()
        _LOGGER.debug("recorded '%s' feedback for suggestion %s", feedback, suggestion_id)

    async def _upload_test_signal(call: ServiceCall) -> None:
        # Inject one synthetic ObservationWindow (a climate entity left on while
        # away, with energy) to exercise the round-trip by hand.
        now = dt_util.utcnow()
        entity_id = call.data.get("entity_id", "climate.test")
        duration_s = float(call.data.get("duration_s", 8 * 3600))
        observation = {
            "entity_id": entity_id,
            "domain": entity_id.split(".", 1)[0],
            "area_id": call.data.get("area_id"),
            "energy_kwh": call.data.get("energy_kwh", 3.2),
            "on_events": [
                {
                    "start": (now - timedelta(seconds=duration_s)).isoformat(),
                    "duration_s": duration_s,
                    "manual": True,
                    "away": True,
                }
            ],
        }
        request = build_observation_upload_request(
            window_start=now - _HISTORY_LOOKBACK,
            window_end=now,
            had_presence_data=True,
            observations=apply_privacy([observation]),
        )
        suggestions = await uploader.upload(request)
        await deliver_suggestions(hass, store, suggestions)
        await store.save()

    cancel = async_track_time_interval(hass, _poll, DEFAULT_POLL_INTERVAL)
    cancel_action = hass.bus.async_listen(
        EVENT_MOBILE_APP_NOTIFICATION_ACTION, _on_notification_action
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "uploader": uploader,
        "store": store,
        "cancel_poll": cancel,
        "cancel_action": cancel_action,
    }
    hass.services.async_register(DOMAIN, SERVICE_UPLOAD_TEST_SIGNAL, _upload_test_signal)
    _LOGGER.info("homapel_insights set up for entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and (cancel := data.get("cancel_poll")):
        cancel()
    if data and (cancel_action := data.get("cancel_action")):
        cancel_action()
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_UPLOAD_TEST_SIGNAL)
    return True
