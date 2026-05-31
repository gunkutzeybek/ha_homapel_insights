"""Surface pulled suggestions as HA notifications (Phase 0 delivery channel)."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def deliver_suggestions(hass: HomeAssistant, suggestions: list[dict]) -> None:
    """Fire a persistent_notification per pending suggestion.

    Phase 1 adds accept/reject actionable notifications wired back through
    `InsightsUploader.send_feedback`.
    """
    for s in suggestions:
        suggestion_id = s.get("suggestion_id", "unknown")
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": f"{DOMAIN}_{suggestion_id}",
                "title": s.get("title", "Laris"),
                "message": s.get("body", ""),
            },
            blocking=False,
        )
        _LOGGER.debug("delivered suggestion %s", suggestion_id)
