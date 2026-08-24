"""Notification button labels follow the home's language."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant

from custom_components.homapel_insights.delivery import _async_button_labels


@pytest.fixture(autouse=True)
def setup_harness(recorder_mock: Any, enable_custom_integrations: None) -> None:
    """Load custom_components/homapel_insights against a stub recorder."""


@pytest.mark.parametrize(
    ("language", "expected"),
    [("tr", ("Evet", "Hayır")), ("en", ("Yes", "No"))],
)
async def test_button_labels_are_translated(
    hass: HomeAssistant, language: str, expected: tuple[str, str]
) -> None:
    hass.config.language = language

    assert await _async_button_labels(hass) == expected
