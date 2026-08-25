"""Config flow — the customer's setup path (CLAUDE.md §2).

    user ──── whole-home opt-in + the API key from laris.homapel.com
                (prefilled from the Homapel Conversation entry when one exists;
                 validated on GET /v1/units/status before the entry is created)

`reauth` swaps a key rotated on the dashboard (started by the upload loop on a
401); `reconfigure` changes the endpoints without touching the key. The entry's
unique_id is the `unit_id` the validation returns — never the api_key itself,
which changes on every rotation.

Per-area / per-entity exclusions are deferred to a later phase; consent is a
single whole-home toggle, and it is checked before anything leaves the house.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_CLOUD_BASE_URL,
    CONF_OPT_IN,
    CONF_UNIT_ID,
    CONF_VOICE_API_BASE,
    DASHBOARD_URL,
    DEFAULT_CLOUD_BASE_URL,
    DEFAULT_VOICE_API_BASE,
    DOMAIN,
    VOICE_CONF_API_BASE,
    VOICE_CONF_API_KEY,
    VOICE_DOMAIN,
)
from .voice_api import (
    UnitStatus,
    VoiceAuthError,
    VoiceConnectionError,
    VoiceForbiddenError,
    async_get_unit_status,
)

_LOGGER = logging.getLogger(__name__)


@callback
def async_voice_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the Homapel Conversation entry to borrow the key/endpoint from."""
    for entry in hass.config_entries.async_entries(VOICE_DOMAIN):
        if entry.data.get(VOICE_CONF_API_KEY):
            return entry
    return None


class HomapelInsightsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @property
    def _placeholders(self) -> dict[str, str]:
        return {"dashboard_url": DASHBOARD_URL}

    async def _async_validate_key(
        self, api_base: str, api_key: str
    ) -> tuple[UnitStatus | None, str | None]:
        """Check a key against the units API. Returns (status, error_key)."""
        session = async_get_clientsession(self.hass)
        try:
            return await async_get_unit_status(session, api_base, api_key), None
        except VoiceAuthError:
            return None, "invalid_auth"
        except VoiceForbiddenError:
            return None, "forbidden"
        except VoiceConnectionError:
            return None, "cannot_connect"
        except Exception:
            _LOGGER.exception("unexpected error validating the Laris api_key")
            return None, "unknown"

    # --- step: user ---------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        voice_entry = async_voice_entry(self.hass)

        if user_input is not None:
            # Consent gate first: without it nothing about this home is even
            # looked up, let alone uploaded.
            if not user_input.get(CONF_OPT_IN):
                errors["base"] = "consent_required"
            else:
                api_key = user_input[CONF_API_KEY].strip()
                voice_api_base = user_input[CONF_VOICE_API_BASE].strip()
                status, error = await self._async_validate_key(voice_api_base, api_key)
                if error:
                    errors["base"] = error
                else:
                    assert status is not None
                    await self.async_set_unique_id(status.unit_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Laris Insights",
                        data={
                            CONF_API_KEY: api_key,
                            CONF_CLOUD_BASE_URL: user_input[CONF_CLOUD_BASE_URL].strip(),
                            CONF_VOICE_API_BASE: voice_api_base,
                            CONF_UNIT_ID: status.unit_id,
                            CONF_OPT_IN: True,
                        },
                    )

        # Prefill from what the customer already typed, else from the voice
        # integration's entry, else from the defaults.
        previous = user_input or {}
        default_key = previous.get(CONF_API_KEY, "")
        default_voice_base = previous.get(CONF_VOICE_API_BASE, DEFAULT_VOICE_API_BASE)
        if voice_entry is not None and not default_key:
            default_key = voice_entry.data[VOICE_CONF_API_KEY]
            default_voice_base = voice_entry.data.get(
                VOICE_CONF_API_BASE, DEFAULT_VOICE_API_BASE
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=default_key): str,
                vol.Required(
                    CONF_CLOUD_BASE_URL,
                    default=previous.get(CONF_CLOUD_BASE_URL, DEFAULT_CLOUD_BASE_URL),
                ): str,
                vol.Required(CONF_VOICE_API_BASE, default=default_voice_base): str,
                vol.Required(CONF_OPT_IN, default=previous.get(CONF_OPT_IN, True)): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=self._placeholders,
        )

    # --- reauth: the key was rotated on the dashboard -----------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The cloud rejected the stored key (401 from the upload loop)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        voice_api_base = entry.data.get(CONF_VOICE_API_BASE, DEFAULT_VOICE_API_BASE)

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            status, error = await self._async_validate_key(voice_api_base, api_key)
            if error:
                errors["base"] = error
            else:
                assert status is not None
                await self.async_set_unique_id(status.unit_id)
                # Entries created before unit_id existed are keyed on the old
                # api_key, so only a known unit_id can disagree with this one.
                if entry.data.get(CONF_UNIT_ID):
                    self._abort_if_unique_id_mismatch(reason="unit_mismatch")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=status.unit_id,
                    data_updates={
                        CONF_API_KEY: api_key,
                        CONF_UNIT_ID: status.unit_id,
                        CONF_VOICE_API_BASE: voice_api_base,
                    },
                )

        # Offer the voice integration's key: a customer who rotated the key has
        # usually already pasted the new one there.
        voice_entry = async_voice_entry(self.hass)
        default_key = voice_entry.data[VOICE_CONF_API_KEY] if voice_entry else ""
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY, default=default_key): str}),
            errors=errors,
            description_placeholders=self._placeholders,
        )

    # --- reconfigure: move the endpoints, keep the key ----------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            voice_api_base = user_input[CONF_VOICE_API_BASE].strip()
            # Re-validate the stored key against the endpoint being set, so a
            # mistyped host is caught here instead of on the next poll.
            status, error = await self._async_validate_key(
                voice_api_base, entry.data[CONF_API_KEY]
            )
            if error:
                errors["base"] = error
            else:
                assert status is not None
                await self.async_set_unique_id(status.unit_id)
                if entry.data.get(CONF_UNIT_ID):
                    self._abort_if_unique_id_mismatch(reason="unit_mismatch")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=status.unit_id,
                    data_updates={
                        CONF_CLOUD_BASE_URL: user_input[CONF_CLOUD_BASE_URL].strip(),
                        CONF_VOICE_API_BASE: voice_api_base,
                        CONF_UNIT_ID: status.unit_id,
                    },
                )

        previous = user_input or entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CLOUD_BASE_URL,
                    default=previous.get(CONF_CLOUD_BASE_URL, DEFAULT_CLOUD_BASE_URL),
                ): str,
                vol.Required(
                    CONF_VOICE_API_BASE,
                    default=previous.get(CONF_VOICE_API_BASE, DEFAULT_VOICE_API_BASE),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders=self._placeholders,
        )
