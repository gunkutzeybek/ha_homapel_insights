"""Signed upload of aggregated observations to the cloud ingest API.

Pull model: the POST response carries this unit's pending suggestions (decision
#5), which the caller delivers as HA notifications. Phase 0 keeps retry/offline
buffering minimal; Phase 1 adds backoff + a Store-backed outbox.
"""

from __future__ import annotations

import logging

from aiohttp import ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)


class InsightsUploader:
    def __init__(self, session: ClientSession, base_url: str, api_key: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def upload(self, request: dict) -> list[dict]:
        """POST an ObservationUploadRequest; return the response's pending suggestions.

        Returns an empty list on any error (failures are non-fatal and retried on
        the next poll — the cloud re-analyzes a trailing window each tick).
        """
        url = f"{self._base_url}/v1/insights/observations"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with self._session.post(
                url, json=request, headers=headers
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("insights upload failed: HTTP %s", resp.status)
                    return []
                data = await resp.json()
                return data.get("pending_suggestions", [])
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("insights upload error: %s", err)
            return []

    async def send_feedback(self, suggestion_id: str, action: str) -> None:
        """POST a user action on a suggestion (§6.3)."""
        url = f"{self._base_url}/v1/insights/feedback"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {"schema_version": 1, "suggestion_id": suggestion_id, "action": action}
        try:
            async with self._session.post(url, json=body, headers=headers) as resp:
                if resp.status != 200:
                    _LOGGER.warning("insights feedback failed: HTTP %s", resp.status)
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("insights feedback error: %s", err)
