"""Execute the action the cloud attached to an accepted suggestion.

The cloud only ships the *idea* (suggestion text + an `automation_draft`); the
side effect runs here on the edge, because only the edge has a path into the
home. Dispatch is by `action.kind`:

  install_automation → install a standing HA automation (persists + recurs),
                       keyed by suggestion_id for idempotency.
  run_action         → run the draft's action steps once now (one-shot).

Everything fails soft: a bad draft logs and returns False rather than killing
the notification-action handler.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.script import Script
from homeassistant.util.yaml import load_yaml, save_yaml

from .const import DOMAIN, KIND_INSTALL_AUTOMATION, KIND_RUN_ACTION

_LOGGER = logging.getLogger(__name__)

_AUTOMATIONS_FILE = "automations.yaml"


async def execute_accepted_action(
    hass: HomeAssistant, suggestion_id: str, kind: str, draft: dict[str, Any] | None
) -> bool:
    """Run the accepted suggestion's side effect. Returns True on success."""
    if kind == KIND_INSTALL_AUTOMATION:
        return await _install_automation(hass, suggestion_id, draft)
    if kind == KIND_RUN_ACTION:
        return await _run_once(hass, suggestion_id, draft)
    _LOGGER.debug("suggestion %s kind %r has no executable action", suggestion_id, kind)
    return False


def _action_steps(draft: dict[str, Any] | None) -> list | None:
    """Pull the executable action sequence out of a draft, if present."""
    if not isinstance(draft, dict):
        return None
    steps = draft.get("action") or draft.get("sequence")
    if not isinstance(steps, list) or not steps:
        return None
    return steps


async def _run_once(
    hass: HomeAssistant, suggestion_id: str, draft: dict[str, Any] | None
) -> bool:
    """Execute the draft's action steps a single time (no trigger installed)."""
    steps = _action_steps(draft)
    if steps is None:
        _LOGGER.warning("run_action suggestion %s has no action steps", suggestion_id)
        return False
    alias = (draft or {}).get("alias", f"{DOMAIN} {suggestion_id}")
    script = Script(hass, steps, alias, DOMAIN)
    try:
        await script.async_run(context=Context())
    except Exception:  # never let a bad draft crash the event handler
        _LOGGER.exception("run_action failed for suggestion %s", suggestion_id)
        return False
    _LOGGER.info("ran one-shot action for suggestion %s", suggestion_id)
    return True


async def _install_automation(
    hass: HomeAssistant, suggestion_id: str, draft: dict[str, Any] | None
) -> bool:
    """Append the draft to automations.yaml and reload.

    Assumes the default config layout (`automation: !include automations.yaml`).
    The automation `id` is the suggestion_id, so re-accepting the same
    suggestion replaces rather than duplicates it.
    """
    if _action_steps(draft) is None:
        _LOGGER.warning(
            "install_automation suggestion %s has no action steps", suggestion_id
        )
        return False

    path = hass.config.path(_AUTOMATIONS_FILE)
    automation = {**draft, "id": suggestion_id}

    try:
        await hass.async_add_executor_job(_upsert_automation, path, automation)
    except Exception:  # malformed file, non-default layout, permissions, …
        _LOGGER.exception(
            "could not install automation for suggestion %s (is %s a plain "
            "list-style automations file?)",
            suggestion_id,
            _AUTOMATIONS_FILE,
        )
        return False

    await hass.services.async_call("automation", "reload", blocking=True)
    _LOGGER.info("installed automation for suggestion %s", suggestion_id)
    return True


def _upsert_automation(path: str, automation: dict[str, Any]) -> None:
    """Load automations.yaml (a list), upsert by id, write it back.

    Runs in the executor — synchronous file IO only.
    """
    existing: list = []
    if os.path.exists(path):
        loaded = load_yaml(path)
        if isinstance(loaded, list):
            existing = loaded
        elif loaded:  # file exists but isn't a plain list — refuse to clobber it
            raise ValueError(f"{path} is not a list-style automations file")

    new_id = automation["id"]
    deduped = [a for a in existing if not (isinstance(a, dict) and a.get("id") == new_id)]
    deduped.append(automation)
    save_yaml(path, deduped)
