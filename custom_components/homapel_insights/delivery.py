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
from homeassistant.helpers.translation import async_get_translations

from .const import (
    ACTION_PREFIX,
    ACTION_SEPARATOR,
    ACTIONABLE_KINDS,
    BTN_ACCEPT,
    BTN_ACCEPT_FALLBACK,
    BTN_ACCEPT_TRANSLATION_KEY,
    BTN_REJECT,
    BTN_REJECT_FALLBACK,
    BTN_REJECT_TRANSLATION_KEY,
    DOMAIN,
    KIND_RUN_ACTION,
    TRANSLATION_CATEGORY_COMMON,
)
from .storage import InsightsStore

_LOGGER = logging.getLogger(__name__)


def _mobile_app_notify_services(hass: HomeAssistant) -> list[str]:
    """Return all registered notify.mobile_app_* service names."""
    notify_services = hass.services.async_services().get("notify", {})
    return [name for name in notify_services if name.startswith("mobile_app_")]


def _encode_action(verb: str, suggestion_id: str) -> str:
    return f"{ACTION_PREFIX}{verb}{ACTION_SEPARATOR}{suggestion_id}"


async def _async_button_labels(hass: HomeAssistant) -> tuple[str, str]:
    """Accept/Reject labels in the home's language (strings.json -> `common`)."""
    translations = await async_get_translations(
        hass, hass.config.language, TRANSLATION_CATEGORY_COMMON, {DOMAIN}
    )
    prefix = f"component.{DOMAIN}.{TRANSLATION_CATEGORY_COMMON}."
    return (
        translations.get(f"{prefix}{BTN_ACCEPT_TRANSLATION_KEY}", BTN_ACCEPT_FALLBACK),
        translations.get(f"{prefix}{BTN_REJECT_TRANSLATION_KEY}", BTN_REJECT_FALLBACK),
    )


def _build_actions(suggestion_id: str, labels: tuple[str, str]) -> list[dict]:
    accept, reject = labels
    return [
        {"action": _encode_action(BTN_ACCEPT, suggestion_id), "title": accept},
        {"action": _encode_action(BTN_REJECT, suggestion_id), "title": reject},
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

    labels = await _async_button_labels(hass)

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
            data["actions"] = _build_actions(suggestion_id, labels)

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
