"""Config flow — whole-home opt-in + cloud endpoint + unit api_key (decision #8).

Per-area / per-entity exclusions are deferred to a later phase; MVP is a single
whole-home consent toggle.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_API_KEY,
    CONF_CLOUD_BASE_URL,
    CONF_OPT_IN,
    DEFAULT_CLOUD_BASE_URL,
    DOMAIN,
)


class HomapelInsightsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_OPT_IN):
                errors["base"] = "consent_required"
            else:
                await self.async_set_unique_id(user_input[CONF_API_KEY])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Laris Insights", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(
                    CONF_CLOUD_BASE_URL, default=DEFAULT_CLOUD_BASE_URL
                ): str,
                vol.Required(CONF_OPT_IN, default=True): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
