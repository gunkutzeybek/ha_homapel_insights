"""Surface pulled suggestions as HA mobile-app notifications.

Actionable suggestions (kind in ACTIONABLE_KINDS) are delivered to every
registered Companion app (notify.mobile_app_*) with Accept/Reject buttons, and
their action draft is stashed so it can be executed when the user taps Accept.
Non-actionable suggestions (info_only / dismiss) are delivered as a plain
message with no buttons.

Tapping a button fires a `mobile_app_notification_action` event whose action
string encodes the verb + suggestion id; `async_setup_entry` listens for it,
runs the stashed action on accept, and reports the choice back to the cloud.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import (
    ACTION_PREFIX,
    ACTION_SEPARATOR,
    ACTIONABLE_KINDS,
    BTN_ACCEPT,
    BTN_REJECT,
    DOMAIN,
    KIND_RUN_ACTION,
)
from .storage import InsightsStore

_LOGGER = logging.getLogger(__name__)


def _mobile_app_notify_services(hass: HomeAssistant) -> list[str]:
    """Return all registered notify.mobile_app_* service names."""
    notify_services = hass.services.async_services().get("notify", {})
    return [name for name in notify_services if name.startswith("mobile_app_")]


def _encode_action(verb: str, suggestion_id: str) -> str:
    return f"{ACTION_PREFIX}{verb}{ACTION_SEPARATOR}{suggestion_id}"


def _build_actions(suggestion_id: str) -> list[dict]:
    return [
        {"action": _encode_action(BTN_ACCEPT, suggestion_id), "title": "Evet"},
        {"action": _encode_action(BTN_REJECT, suggestion_id), "title": "Hayır"},
    ]


async def deliver_suggestions(
    hass: HomeAssistant, store: InsightsStore, suggestions: list[dict]
) -> None:
    """Send one notification per suggestion to every mobile app.

    Actionable suggestions get Accept/Reject buttons and have their draft
    stashed in `store` for later execution. The caller is responsible for
    persisting the store afterwards.
    """
    services = _mobile_app_notify_services(hass)
    if not services:
        _LOGGER.warning(
            "no mobile_app notify services found; install the Home Assistant "
            "Companion app to receive actionable insight notifications"
        )
        return

    for s in suggestions:
        suggestion_id = s.get("suggestion_id", "unknown")
        action = s.get("action") or {}
        kind = action.get("kind", "info_only")
        actionable = kind in ACTIONABLE_KINDS

        data: dict = {"tag": f"{DOMAIN}_{suggestion_id}"}
        if actionable:
            # Stash the kind-appropriate payload so the executor can run it on
            # Accept: install_automation carries `automation_draft` (persisted),
            # run_action carries `action_payload` ({"sequence": [...]}, one-shot).
            draft = (
                action.get("action_payload")
                if kind == KIND_RUN_ACTION
                else action.get("automation_draft")
            )
            store.stash_action(suggestion_id, kind, draft)
            data["actions"] = _build_actions(suggestion_id)

        payload = {
            "title": s.get("title", "Laris"),
            "message": s.get("body", ""),
            "data": data,
        }
        for service in services:
            await hass.services.async_call("notify", service, payload, blocking=False)
        _LOGGER.debug(
            "delivered suggestion %s (kind=%s, actionable=%s) to %d mobile app(s)",
            suggestion_id,
            kind,
            actionable,
            len(services),
        )
