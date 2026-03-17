"""Tests for the Legrand RFLC light platform."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.legrand_rflc.const import DOMAIN, LegrandRFLCData
from custom_components.legrand_rflc.hub import Composer

from .conftest import MOCK_HOST, MOCK_MAC, MockHub, make_zone

INIT_PATCH = "custom_components.legrand_rflc"


@pytest.fixture
async def setup_lights(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_hub: MockHub,
) -> MockHub:
    """Set up the integration and return the mock hub."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(f"{INIT_PATCH}.Connector") as mock_conn_cls,
        patch(f"{INIT_PATCH}.Hub", return_value=mock_hub),
    ):
        mock_conn_cls.return_value.loop = AsyncMock(return_value=MOCK_MAC)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    return mock_hub


# ---- Entity creation ----


async def test_dimmer_entity_created(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test a dimmer zone creates a light entity with brightness."""
    state = hass.states.get("light.living_room")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes.get(ATTR_BRIGHTNESS) is not None


async def test_switch_entity_created(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test a switch zone creates a light entity without brightness."""
    state = hass.states.get("light.kitchen")
    assert state is not None
    assert state.state == STATE_OFF


# ---- State updates via events ----


async def test_zone_properties_changed(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test entity state updates on zone property change events."""
    hub = setup_lights

    # Simulate the hub pushing a property change.
    await hub.emit(
        f"{hub.EVENT_ZONE_PROPERTIES_CHANGED}:1",
        {
            hub.SERVICE: "ZonePropertiesChanged",
            hub.ZID: 1,
            hub.PROPERTY_LIST: {hub.POWER: True},
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.kitchen")
    assert state is not None
    assert state.state == STATE_ON


async def test_dimmer_brightness_update(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test dimmer brightness updates on zone property change."""
    hub = setup_lights

    await hub.emit(
        f"{hub.EVENT_ZONE_PROPERTIES_CHANGED}:0",
        {
            hub.SERVICE: "ZonePropertiesChanged",
            hub.ZID: 0,
            hub.PROPERTY_LIST: {hub.POWER_LEVEL: 50, hub.POWER: True},
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.living_room")
    assert state is not None
    # 50 / 100 * 255 = 127
    assert state.attributes[ATTR_BRIGHTNESS] == 127


# ---- Commands ----


async def test_switch_turn_on(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test turning on a switch."""
    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.kitchen"},
        blocking=True,
    )
    # No exception means success; the mock hub returned Success.


async def test_switch_turn_off(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test turning off a switch."""
    await hass.services.async_call(
        "light",
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "light.kitchen"},
        blocking=True,
    )


async def test_dimmer_turn_on_with_brightness(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test turning on a dimmer with brightness."""
    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.living_room", ATTR_BRIGHTNESS: 128},
        blocking=True,
    )


async def test_command_error_raises_ha_error(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test that a hub error response raises HomeAssistantError."""
    hub = setup_lights
    hub._set_zone_response = {
        "Status": "Error",
        "ErrorCode": "99",
        "ErrorText": "Zone busy",
    }

    with pytest.raises(HomeAssistantError, match="hub error"):
        await hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.kitchen"},
            blocking=True,
        )


# ---- Availability ----


async def test_availability_tracks_connection(
    hass: HomeAssistant, setup_lights: MockHub
) -> None:
    """Test entity becomes unavailable when hub disconnects."""
    hub = setup_lights

    hub.connected = False
    await hub.emit(hub.EVENT_DISCONNECTED)
    await hass.async_block_till_done()

    state = hass.states.get("light.living_room")
    assert state is not None
    assert state.state == "unavailable"

    hub.connected = True
    hub.authenticated = True
    await hub.emit(hub.EVENT_AUTHENTICATED, MOCK_HOST)
    await hass.async_block_till_done()

    state = hass.states.get("light.living_room")
    assert state is not None
    assert state.state != "unavailable"


# ---- Brightness normalization ----


async def test_brightness_normalization() -> None:
    """Test brightness conversion between HA (0-255) and LC7001 (0-100)."""
    from custom_components.legrand_rflc.light import _Dimmer

    # LC7001 0 → HA 0
    assert _Dimmer._to_ha(0) == 0
    # LC7001 100 → HA 255
    assert _Dimmer._to_ha(100) == 255
    # LC7001 50 → HA 127
    assert _Dimmer._to_ha(50) == 127

    # HA 0 → LC7001 0
    assert _Dimmer._from_ha(0) == 0
    # HA 255 → LC7001 100
    assert _Dimmer._from_ha(255) == 100
    # HA 127 → LC7001 49 (truncation)
    assert _Dimmer._from_ha(127) == 49
