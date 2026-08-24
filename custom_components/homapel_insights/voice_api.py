"""Cheap API-key validation against the Laris cloud (`agentic_service`).

The insights ingest has no validation endpoint of its own, so setup reuses the
voice backend's `GET /v1/units/status` — the same call the voice integration
makes with the same Bearer key. It is cheap (one row + an ETag) and it returns
the `unit_id`, which is what the config entry keys itself on.

Only the two fields the config flow needs are parsed; everything else in the
response belongs to the voice integration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import STATUS_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class VoiceApiError(Exception):
    """Base error talking to the units API."""


class VoiceAuthError(VoiceApiError):
    """401 — no unit owns this api_key (revoked or mistyped)."""


class VoiceForbiddenError(VoiceApiError):
    """403 — the unit exists but its subscription is not live."""


class VoiceConnectionError(VoiceApiError):
    """Transport error, timeout, or an unexpected status."""


@dataclass(slots=True)
class UnitStatus:
    """The slice of `GET /v1/units/status` this integration cares about."""

    unit_id: str
    active: bool


async def async_get_unit_status(
    session: ClientSession, api_base: str, api_key: str
) -> UnitStatus:
    """Validate `api_key` and return the unit it belongs to.

    A dormant unit (`active: false`) is NOT an error here: the customer may add
    the integration before the subscription goes live, and the upload loop will
    raise a repair issue if it is still dormant when the first poll runs.
    """
    url = f"{api_base.rstrip('/')}/v1/units/status"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with session.get(
            url, headers=headers, timeout=ClientTimeout(total=STATUS_TIMEOUT)
        ) as resp:
            if resp.status == 401:
                raise VoiceAuthError("invalid api_key")
            if resp.status == 403:
                raise VoiceForbiddenError("unit not active")
            if resp.status != 200:
                raise VoiceConnectionError(f"unexpected status {resp.status}")
            data = await resp.json()
    except (ClientError, TimeoutError) as err:
        raise VoiceConnectionError(str(err)) from err

    unit_id = data.get("unit_id")
    if not unit_id:
        raise VoiceConnectionError("status response carried no unit_id")
    return UnitStatus(unit_id=str(unit_id), active=bool(data.get("active", False)))
