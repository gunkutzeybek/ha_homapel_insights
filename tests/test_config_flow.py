"""Config flow — the customer's setup path (CLAUDE.md §2).

Every test drives the real flow against a mocked `GET /v1/units/status`, the
cheap key check the flow leans on. `async_setup_entry` is patched out: these
tests are about onboarding, not about the hourly poll.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.homapel_insights.const import (
    CONF_API_KEY,
    CONF_CLOUD_BASE_URL,
    CONF_OPT_IN,
    CONF_UNIT_ID,
    CONF_VOICE_API_BASE,
    DOMAIN,
    VOICE_CONF_API_BASE,
    VOICE_CONF_API_KEY,
    VOICE_DOMAIN,
)

API_KEY = "laris_key_1"
NEW_API_KEY = "laris_key_2"
VOICE_API_BASE = "https://api.test"
CLOUD_BASE_URL = "https://insights.test"
UNIT_ID = "unit-1234"
OTHER_UNIT_ID = "unit-9999"
STATUS_URL = f"{VOICE_API_BASE}/v1/units/status"

USER_INPUT = {
    CONF_API_KEY: API_KEY,
    CONF_CLOUD_BASE_URL: CLOUD_BASE_URL,
    CONF_VOICE_API_BASE: VOICE_API_BASE,
    CONF_OPT_IN: True,
}


@pytest.fixture(autouse=True)
def setup_harness(recorder_mock: Any, enable_custom_integrations: None) -> None:
    """Load custom_components/homapel_insights against a stub recorder.

    `recorder_mock` must be requested before anything that builds `hass` (the
    harness asserts on that), which is why the two live in one fixture.
    """


@pytest.fixture
def mock_setup_entry():
    """Onboarding tests never want the hourly poll to actually start."""
    with patch(
        "custom_components.homapel_insights.async_setup_entry", return_value=True
    ) as mock:
        yield mock


def mock_status(
    aioclient_mock: AiohttpClientMocker,
    *,
    status: int = 200,
    unit_id: str = UNIT_ID,
    active: bool = True,
    exc: Exception | None = None,
) -> None:
    """Register the units API's answer for this test."""
    aioclient_mock.clear_requests()
    if exc is not None:
        aioclient_mock.get(STATUS_URL, exc=exc)
    elif status != 200:
        aioclient_mock.get(
            STATUS_URL,
            status=status,
            json={"error": {"code": "nope", "message": "nope"}},
        )
    else:
        aioclient_mock.get(
            STATUS_URL,
            json={"unit_id": unit_id, "active": active, "updated_at": "2026-08-24T00:00:00Z"},
        )


def schema_defaults(result: dict[str, Any]) -> dict[str, Any]:
    """The prefilled values a form is showing the customer."""
    schema: vol.Schema = result["data_schema"]
    return {
        str(key): key.default()
        for key in schema.schema
        if isinstance(key, vol.Marker) and key.default is not vol.UNDEFINED
    }


def insights_entry(hass: HomeAssistant, **overrides: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=overrides.pop("unique_id", UNIT_ID),
        data={
            CONF_API_KEY: API_KEY,
            CONF_CLOUD_BASE_URL: CLOUD_BASE_URL,
            CONF_VOICE_API_BASE: VOICE_API_BASE,
            CONF_UNIT_ID: UNIT_ID,
            CONF_OPT_IN: True,
            **overrides,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def start_user_flow(hass: HomeAssistant) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


# --- step: user ---------------------------------------------------------------


async def test_user_flow_validates_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_setup_entry
) -> None:
    """A key the cloud accepts creates an entry keyed on the unit_id."""
    mock_status(aioclient_mock)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {**USER_INPUT, CONF_UNIT_ID: UNIT_ID}
    assert result["result"].unique_id == UNIT_ID
    # The key was checked against the units API before the entry was created.
    assert aioclient_mock.call_count == 1
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {API_KEY}"


async def test_user_flow_accepts_a_dormant_unit(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_setup_entry
) -> None:
    """Installing before the subscription goes live is allowed (the poll repairs)."""
    mock_status(aioclient_mock, active=False)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"status": 401}, "invalid_auth"),
        ({"status": 403}, "forbidden"),
        ({"status": 500}, "cannot_connect"),
        ({"exc": ClientError("boom")}, "cannot_connect"),
        ({"exc": TimeoutError()}, "cannot_connect"),
    ],
)
async def test_user_flow_key_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict[str, Any],
    expected: str,
) -> None:
    """A rejected or unreachable key keeps the customer on the form."""
    mock_status(aioclient_mock, **kwargs)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    # What was typed is still there, so only the wrong field has to change.
    assert schema_defaults(result)[CONF_API_KEY] == API_KEY


async def test_user_flow_recovers_after_a_bad_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_setup_entry
) -> None:
    mock_status(aioclient_mock, status=401)
    result = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}

    mock_status(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_API_KEY: NEW_API_KEY}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_KEY] == NEW_API_KEY


async def test_user_flow_requires_consent(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The opt-in gate is checked first — nothing is looked up without it."""
    mock_status(aioclient_mock)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_OPT_IN: False}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "consent_required"}
    assert aioclient_mock.call_count == 0


async def test_user_flow_aborts_when_the_unit_is_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    insights_entry(hass)
    mock_status(aioclient_mock)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- reusing the Homapel Conversation key -------------------------------------


async def test_user_flow_prefills_from_conversation_entry(hass: HomeAssistant) -> None:
    """The voice integration already holds this key; don't make them retype it."""
    MockConfigEntry(
        domain=VOICE_DOMAIN,
        data={VOICE_CONF_API_KEY: API_KEY, VOICE_CONF_API_BASE: VOICE_API_BASE},
    ).add_to_hass(hass)

    defaults = schema_defaults(await start_user_flow(hass))

    assert defaults[CONF_API_KEY] == API_KEY
    assert defaults[CONF_VOICE_API_BASE] == VOICE_API_BASE


async def test_user_flow_has_no_prefill_without_the_voice_integration(
    hass: HomeAssistant,
) -> None:
    defaults = schema_defaults(await start_user_flow(hass))

    assert defaults[CONF_API_KEY] == ""
    assert defaults[CONF_VOICE_API_BASE] != ""


# --- reauth -------------------------------------------------------------------


async def test_reauth_swaps_a_rotated_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_setup_entry
) -> None:
    entry = insights_entry(hass)
    mock_status(aioclient_mock)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: NEW_API_KEY}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == NEW_API_KEY
    assert entry.unique_id == UNIT_ID


async def test_reauth_rejects_a_key_from_another_unit(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = insights_entry(hass)
    mock_status(aioclient_mock, unit_id=OTHER_UNIT_ID)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: NEW_API_KEY}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unit_mismatch"
    assert entry.data[CONF_API_KEY] == API_KEY


async def test_reauth_keeps_the_form_on_a_bad_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = insights_entry(hass)
    mock_status(aioclient_mock, status=401)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: NEW_API_KEY}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_adopts_the_unit_id_of_a_legacy_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_setup_entry
) -> None:
    """Entries created before unit_id existed are keyed on the api_key itself."""
    entry = insights_entry(hass, unique_id=API_KEY, **{CONF_UNIT_ID: None})
    hass.config_entries.async_update_entry(
        entry, data={k: v for k, v in entry.data.items() if k != CONF_UNIT_ID}
    )
    mock_status(aioclient_mock)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: NEW_API_KEY}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == UNIT_ID
    assert entry.data[CONF_UNIT_ID] == UNIT_ID


# --- reconfigure --------------------------------------------------------------


async def test_reconfigure_moves_the_endpoints(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_setup_entry
) -> None:
    entry = insights_entry(hass)
    mock_status(aioclient_mock)

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    assert schema_defaults(result)[CONF_CLOUD_BASE_URL] == CLOUD_BASE_URL

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLOUD_BASE_URL: "https://insights.staging.test",
            CONF_VOICE_API_BASE: VOICE_API_BASE,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CLOUD_BASE_URL] == "https://insights.staging.test"
    # The stored key is re-checked against the endpoint being set.
    assert entry.data[CONF_API_KEY] == API_KEY


async def test_reconfigure_reports_an_unreachable_endpoint(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = insights_entry(hass)
    mock_status(aioclient_mock, exc=ClientError("boom"))

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CLOUD_BASE_URL: CLOUD_BASE_URL, CONF_VOICE_API_BASE: VOICE_API_BASE},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
