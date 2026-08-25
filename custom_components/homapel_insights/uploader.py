"""Signed upload of aggregated observations to the cloud ingest API.

Pull model: the POST response carries this unit's pending suggestions (decision
#5), which the caller delivers as HA notifications. Phase 0 keeps retry/offline
buffering minimal; Phase 1 adds backoff + a Store-backed outbox.

Auth failures are the one class of error the customer has to act on, so they are
surfaced instead of logged:

* **401** — the key was rotated or revoked. Starts a reauth flow, which HA shows
  as a fixable repair ("Reconfigure Laris Insights") leading to `reauth_confirm`.
* **403** — the key is fine but the subscription is not live. Raises the
  `unit_not_active` repair issue pointing at the dashboard.

Both are cleared by the next successful call.
"""

from __future__ import annotations

import logging

from aiohttp import ClientError, ClientResponse, ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    DASHBOARD_URL,
    DOMAIN,
    ISSUE_UNIT_NOT_ACTIVE,
    SCHEMA_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# `/insights/feedback` 403s a suggestion that belongs to a different unit. That
# is not a subscription problem, so it must not raise the repair issue.
CODE_NOT_YOUR_SUGGESTION = "not_your_suggestion"


async def _error_code(resp: ClientResponse) -> str | None:
    """Read `code` out of the cloud's {"error": {...}} envelope, if it has one.

    FastAPI wraps an HTTPException `detail` in {"detail": ...}, so the envelope
    can be at either level; anything unparsable reads as "no code".
    """
    try:
        body = await resp.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    envelope = body.get("detail", body)
    if isinstance(envelope, dict) and isinstance(error := envelope.get("error"), dict):
        code = error.get("code")
        return str(code) if code is not None else None
    return None


class InsightsUploader:
    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        base_url: str,
        api_key: str,
        entry: ConfigEntry,
    ) -> None:
        self._hass = hass
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._entry = entry

    # --- repair issues ------------------------------------------------------

    @property
    def _not_active_issue_id(self) -> str:
        return f"{ISSUE_UNIT_NOT_ACTIVE}_{self._entry.entry_id}"

    async def _handle_error_status(self, resp: ClientResponse) -> None:
        """Turn a 401/403 into something the customer can actually see."""
        if resp.status == 401:
            # HA renders the reauth flow as its own repair issue; raising a
            # second one for the same problem would just double the noise.
            self._entry.async_start_reauth(self._hass)
        elif resp.status == 403 and await _error_code(resp) != CODE_NOT_YOUR_SUGGESTION:
            # A 403 from the auth dependency means the subscription is not live.
            # /feedback also 403s a suggestion belonging to another unit, which
            # says nothing about the subscription — that one is just a bug.
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                self._not_active_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_UNIT_NOT_ACTIVE,
                translation_placeholders={"dashboard_url": DASHBOARD_URL},
                learn_more_url=DASHBOARD_URL,
            )

    def _clear_auth_issues(self) -> None:
        ir.async_delete_issue(self._hass, DOMAIN, self._not_active_issue_id)

    # --- calls --------------------------------------------------------------

    async def upload(self, request: dict) -> list[dict]:
        """POST an ObservationUploadRequest; return the response's pending suggestions.

        Returns an empty list on any error (failures are non-fatal and retried on
        the next poll — the cloud re-analyzes a trailing window each tick).
        """
        url = f"{self._base_url}/v1/insights/observations"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with self._session.post(url, json=request, headers=headers) as resp:
                if resp.status != 200:
                    await self._handle_error_status(resp)
                    _LOGGER.warning("insights upload failed: HTTP %s", resp.status)
                    return []
                self._clear_auth_issues()
                data = await resp.json()
                return data.get("pending_suggestions", [])
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("insights upload error: %s", err)
            return []

    async def send_feedback(self, suggestion_id: str, action: str) -> None:
        """POST a user action on a suggestion (§6.3)."""
        url = f"{self._base_url}/v1/insights/feedback"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {
            "schema_version": SCHEMA_VERSION,
            "suggestion_id": suggestion_id,
            "action": action,
        }
        try:
            async with self._session.post(url, json=body, headers=headers) as resp:
                if resp.status != 200:
                    await self._handle_error_status(resp)
                    _LOGGER.warning("insights feedback failed: HTTP %s", resp.status)
                else:
                    self._clear_auth_issues()
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("insights feedback error: %s", err)
