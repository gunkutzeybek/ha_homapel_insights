"""Upload/feedback auth failures are surfaced, not logged.

401 hands the customer a reauth flow (HA renders it as a repair); 403 raises the
`unit_not_active` repair issue. Both go away on the next successful call.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.homapel_insights.const import (
    CONF_API_KEY,
    CONF_CLOUD_BASE_URL,
    CONF_OPT_IN,
    CONF_UNIT_ID,
    CONF_VOICE_API_BASE,
    DOMAIN,
    FEEDBACK_ACCEPTED,
    ISSUE_UNIT_NOT_ACTIVE,
    SCHEMA_VERSION,
)
from custom_components.homapel_insights.uploader import InsightsUploader

API_KEY = "laris_key_1"
CLOUD_BASE_URL = "https://insights.test"
OBSERVATIONS_URL = f"{CLOUD_BASE_URL}/v1/insights/observations"
FEEDBACK_URL = f"{CLOUD_BASE_URL}/v1/insights/feedback"
SUGGESTION_ID = "0f1c0d2e-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def setup_harness(recorder_mock: Any, enable_custom_integrations: None) -> None:
    """Load custom_components/homapel_insights against a stub recorder."""


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="unit-1234",
        data={
            CONF_API_KEY: API_KEY,
            CONF_CLOUD_BASE_URL: CLOUD_BASE_URL,
            CONF_VOICE_API_BASE: "https://api.test",
            CONF_UNIT_ID: "unit-1234",
            CONF_OPT_IN: True,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


@pytest.fixture
def uploader(hass: HomeAssistant, entry: MockConfigEntry) -> InsightsUploader:
    return InsightsUploader(
        hass=hass,
        session=async_get_clientsession(hass),
        base_url=CLOUD_BASE_URL,
        api_key=API_KEY,
        entry=entry,
    )


def not_active_issue(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"{ISSUE_UNIT_NOT_ACTIVE}_{entry.entry_id}"
    )


def error(code: str) -> dict[str, Any]:
    return {"detail": {"error": {"code": code, "message": code}}}


async def test_upload_returns_pending_suggestions(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, uploader: InsightsUploader
) -> None:
    aioclient_mock.post(OBSERVATIONS_URL, json={"pending_suggestions": [{"a": 1}]})

    assert await uploader.upload({"observations": []}) == [{"a": 1}]
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {API_KEY}"


async def test_feedback_posts_the_current_schema_version(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, uploader: InsightsUploader
) -> None:
    aioclient_mock.post(FEEDBACK_URL, json={})

    await uploader.send_feedback(SUGGESTION_ID, FEEDBACK_ACCEPTED)

    assert aioclient_mock.mock_calls[0][2] == {
        "schema_version": SCHEMA_VERSION,
        "suggestion_id": SUGGESTION_ID,
        "action": FEEDBACK_ACCEPTED,
    }


async def test_401_starts_a_reauth_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    uploader: InsightsUploader,
    entry: MockConfigEntry,
) -> None:
    aioclient_mock.post(OBSERVATIONS_URL, status=401, json=error("invalid_api_key"))

    assert await uploader.upload({"observations": []}) == []
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(
        DOMAIN, match_context={"source": SOURCE_REAUTH}
    )
    assert len(flows) == 1
    assert not_active_issue(hass, entry) is None


async def test_403_raises_the_subscription_issue(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    uploader: InsightsUploader,
    entry: MockConfigEntry,
) -> None:
    aioclient_mock.post(OBSERVATIONS_URL, status=403, json=error("unit_not_active"))

    assert await uploader.upload({"observations": []}) == []

    issue = not_active_issue(hass, entry)
    assert issue is not None
    assert issue.translation_key == ISSUE_UNIT_NOT_ACTIVE
    assert issue.severity is ir.IssueSeverity.ERROR


async def test_a_successful_upload_clears_the_issue(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    uploader: InsightsUploader,
    entry: MockConfigEntry,
) -> None:
    aioclient_mock.post(OBSERVATIONS_URL, status=403, json=error("unit_not_active"))
    await uploader.upload({"observations": []})
    assert not_active_issue(hass, entry) is not None

    aioclient_mock.clear_requests()
    aioclient_mock.post(OBSERVATIONS_URL, json={"pending_suggestions": []})
    await uploader.upload({"observations": []})

    assert not_active_issue(hass, entry) is None


async def test_a_foreign_suggestion_is_not_a_subscription_problem(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    uploader: InsightsUploader,
    entry: MockConfigEntry,
) -> None:
    """/feedback 403s a suggestion owned by another unit — that says nothing
    about this unit's subscription."""
    aioclient_mock.post(FEEDBACK_URL, status=403, json=error("not_your_suggestion"))

    await uploader.send_feedback(SUGGESTION_ID, FEEDBACK_ACCEPTED)

    assert not_active_issue(hass, entry) is None
