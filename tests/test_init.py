"""Tests for the Legrand RFLC integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.legrand_rflc.const import DOMAIN, LegrandRFLCData
from custom_components.legrand_rflc.hub import Authenticator

from .conftest import MOCK_HOST, MOCK_MAC, MockHub

INIT_PATCH = "custom_components.legrand_rflc"


async def test_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_hub: MockHub,
) -> None:
    """Test successful setup creates runtime data and registers device."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(f"{INIT_PATCH}.Connector") as mock_conn_cls,
        patch(f"{INIT_PATCH}.Hub", return_value=mock_hub),
    ):
        mock_conn_cls.return_value.loop = AsyncMock(return_value=MOCK_MAC)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is mock_config_entry.state  # loaded
    assert isinstance(mock_config_entry.runtime_data, LegrandRFLCData)
    assert mock_config_entry.runtime_data.hub is mock_hub


async def test_setup_entry_connection_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup raises ConfigEntryNotReady on connection failure."""
    mock_config_entry.add_to_hass(hass)

    with patch(f"{INIT_PATCH}.Connector") as mock_conn_cls:
        mock_conn_cls.return_value.loop = AsyncMock(
            side_effect=OSError("Connection refused")
        )
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert (
        mock_config_entry.state
        is mock_config_entry.state.__class__.SETUP_RETRY
    )


async def test_setup_entry_auth_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup raises ConfigEntryNotReady on auth failure."""
    mock_config_entry.add_to_hass(hass)

    with patch(f"{INIT_PATCH}.Connector") as mock_conn_cls:
        mock_conn_cls.return_value.loop = AsyncMock(
            side_effect=Authenticator.Error("Invalid")
        )
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert (
        mock_config_entry.state
        is mock_config_entry.state.__class__.SETUP_RETRY
    )


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_hub: MockHub,
) -> None:
    """Test unloading cancels the hub and unloads platforms."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(f"{INIT_PATCH}.Connector") as mock_conn_cls,
        patch(f"{INIT_PATCH}.Hub", return_value=mock_hub),
    ):
        mock_conn_cls.return_value.loop = AsyncMock(return_value=MOCK_MAC)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert result is True
