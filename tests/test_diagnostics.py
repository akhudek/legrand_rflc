"""Tests for the Legrand RFLC diagnostics platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_AUTHENTICATION, CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.legrand_rflc.const import DOMAIN, LegrandRFLCData
from custom_components.legrand_rflc.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import MOCK_HOST, MOCK_KEY_HEX, MOCK_MAC, MockHub, make_zone


async def test_diagnostics_connected(hass: HomeAssistant) -> None:
    """Test diagnostics when hub is connected."""
    hub = MockHub(
        zones=[make_zone(0, "Living Room", "Dimmer", True, 75)],
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_MAC: MOCK_MAC,
            CONF_AUTHENTICATION: MOCK_KEY_HEX,
        },
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)
    entry.runtime_data = LegrandRFLCData(hub=hub)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["hub"]["connected"] is True
    assert diag["hub"]["authenticated"] is True
    assert diag["hub"]["host"] == MOCK_HOST
    # Auth key should be redacted.
    assert diag["config_entry"][CONF_AUTHENTICATION] == "**REDACTED**"
    assert "zones" in diag
    assert len(diag["zones"]) == 1
    assert diag["zones"][0]["zid"] == 0


async def test_diagnostics_disconnected(hass: HomeAssistant) -> None:
    """Test diagnostics when hub is disconnected."""
    hub = MockHub()
    hub.connected = False
    hub.authenticated = False

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: MOCK_HOST, CONF_MAC: MOCK_MAC},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)
    entry.runtime_data = LegrandRFLCData(hub=hub)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["hub"]["connected"] is False
    assert "zones" not in diag
