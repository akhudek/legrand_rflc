"""Tests for the Legrand RFLC config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.legrand_rflc.const import DOMAIN
from custom_components.legrand_rflc.hub import Authenticator

from .conftest import MOCK_HOST, MOCK_KEY_HEX, MOCK_MAC

PATCH = "custom_components.legrand_rflc.config_flow"


# ---- User step ----


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Test that the user step shows a form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_success(hass: HomeAssistant) -> None:
    """Test successful user flow creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(f"{PATCH}.Connector") as mock_conn:
        mock_conn.return_value.loop = AsyncMock(return_value=MOCK_MAC)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_HOST
    assert result["data"][CONF_HOST] == MOCK_HOST
    assert result["data"][CONF_MAC] == MOCK_MAC
    assert CONF_AUTHENTICATION not in result["data"]


async def test_user_step_with_password(hass: HomeAssistant) -> None:
    """Test user flow with password stores auth key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(f"{PATCH}.Connector") as mock_conn,
        patch(f"{PATCH}.hash_password", return_value=b"\x01" * 16),
    ):
        mock_conn.return_value.loop = AsyncMock(return_value=MOCK_MAC)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST, CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_AUTHENTICATION in result["data"]
    assert result["data"][CONF_AUTHENTICATION] == ("01" * 16)


async def test_user_step_invalid_host(hass: HomeAssistant) -> None:
    """Test user flow with unreachable host shows error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(f"{PATCH}.Connector") as mock_conn:
        mock_conn.return_value.loop = AsyncMock(
            side_effect=OSError("Connection refused")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_user_step_invalid_auth(hass: HomeAssistant) -> None:
    """Test user flow with bad password shows error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(f"{PATCH}.Connector") as mock_conn,
        patch(f"{PATCH}.hash_password", return_value=b"\x01" * 16),
    ):
        mock_conn.return_value.loop = AsyncMock(
            side_effect=Authenticator.Error("Invalid")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST, CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PASSWORD: "invalid_auth"}


async def test_user_step_already_configured(hass: HomeAssistant) -> None:
    """Test user flow aborts if entry already exists."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: MOCK_HOST, CONF_MAC: MOCK_MAC},
        unique_id=MOCK_HOST,
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(f"{PATCH}.Connector") as mock_conn:
        mock_conn.return_value.loop = AsyncMock(return_value=MOCK_MAC)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---- Reauth step ----


async def test_reauth_flow_success(hass: HomeAssistant) -> None:
    """Test successful reauth updates the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: MOCK_HOST, CONF_MAC: MOCK_MAC},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": MOCK_HOST,
        },
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(f"{PATCH}.Connector") as mock_conn,
        patch(f"{PATCH}.hash_password", return_value=b"\x02" * 16),
    ):
        mock_conn.return_value.loop = AsyncMock(return_value=MOCK_MAC)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "newpass"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Test reauth with bad password shows error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: MOCK_HOST, CONF_MAC: MOCK_MAC},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": MOCK_HOST,
        },
        data=entry.data,
    )

    with (
        patch(f"{PATCH}.Connector") as mock_conn,
        patch(f"{PATCH}.hash_password", return_value=b"\x02" * 16),
    ):
        mock_conn.return_value.loop = AsyncMock(
            side_effect=Authenticator.Error("Invalid")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PASSWORD: "invalid_auth"}


# ---- Reconfigure step ----


async def test_reconfigure_flow_success(hass: HomeAssistant) -> None:
    """Test successful reconfigure updates the entry."""
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

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_host = "192.168.1.200"
    with patch(f"{PATCH}.Connector") as mock_conn:
        mock_conn.return_value.loop = AsyncMock(return_value="aabbccddeeff")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: new_host},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == new_host
    # Previous auth key should be preserved since no new password given.
    assert entry.data[CONF_AUTHENTICATION] == MOCK_KEY_HEX


async def test_reconfigure_flow_invalid_host(hass: HomeAssistant) -> None:
    """Test reconfigure with bad host shows error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: MOCK_HOST, CONF_MAC: MOCK_MAC},
        unique_id=MOCK_HOST,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    with patch(f"{PATCH}.Connector") as mock_conn:
        mock_conn.return_value.loop = AsyncMock(
            side_effect=OSError("Unreachable")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "bad-host"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}
