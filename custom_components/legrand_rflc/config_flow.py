"""Config flow for Legrand RFLC integration."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Mapping
from typing import Any, Final

import voluptuous

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
)

from .const import DOMAIN
from .hub import Authenticator, Connector, hash_password

_LOGGER: Final = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """ConfigFlow for Legrand RFLC integration."""

    VERSION = 1

    HOST: Final = Connector.HOST

    ABORT_NO_DEVICES_FOUND: Final = "no_devices_found"
    ABORT_REAUTH_SUCCESSFUL: Final = "reauth_successful"
    ABORT_RECONFIGURE_SUCCESSFUL: Final = "reconfigure_successful"

    ERROR_INVALID_HOST: Final = "invalid_host"
    ERROR_INVALID_AUTH: Final = "invalid_auth"

    async def _test_connection(
        self,
        host: str,
        key: bytes | None = None,
        port: int | None = None,
    ) -> str:
        """Test connection and return MAC address.

        Raises OSError on connection failure.
        Raises Authenticator.Error on authentication failure.
        """
        kwargs: dict[str, Any] = {"key": key, "loop_timeout": -1}
        if port is not None:
            kwargs["port"] = port
        connector = Connector(host, **kwargs)
        return await connector.loop()

    async def async_step_dhcp(
        self, discovery_info: Any
    ) -> ConfigFlowResult:
        """Handle a flow initiated by dhcp discovery."""
        try:
            resolutions = await asyncio.get_running_loop().getaddrinfo(
                self.HOST, None
            )
        except OSError as error:
            _LOGGER.warning("OS getaddrinfo %s error %s", self.HOST, error)
            return self.async_abort(reason=self.ABORT_NO_DEVICES_FOUND)
        address: str = discovery_info.ip if hasattr(discovery_info, "ip") else discovery_info.get("ip", "")
        if any(
            resolution[4][0] == address
            for resolution in resolutions
            if resolution[0] == socket.AF_INET
        ):
            await self._async_handle_discovery_without_unique_id()
            return await self.async_step_user()
        _LOGGER.warning(
            "%s does not resolve to discovered %s", self.HOST, address
        )
        return self.async_abort(reason=self.ABORT_NO_DEVICES_FOUND)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}
        host = self.HOST
        if user_input is not None:
            host = user_input[CONF_HOST]
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            key: bytes | None = None
            if CONF_PASSWORD in user_input:
                key = hash_password(user_input[CONF_PASSWORD].encode())
            port: int | None = user_input.get(CONF_PORT)
            try:
                mac = await self._test_connection(host, key, port)
            except OSError:
                errors[CONF_HOST] = self.ERROR_INVALID_HOST
            except Authenticator.Error:
                errors[CONF_PASSWORD] = self.ERROR_INVALID_AUTH
            else:
                data: dict[str, Any] = {CONF_HOST: host, CONF_MAC: mac}
                if key is not None:
                    data[CONF_AUTHENTICATION] = key.hex()
                if port is not None:
                    data[CONF_PORT] = port
                return self.async_create_entry(title=host, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=voluptuous.Schema(
                {
                    voluptuous.Required(CONF_HOST, default=host): str,
                    voluptuous.Optional(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth flow entry point."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        host: str = reauth_entry.data[CONF_HOST]

        if user_input is not None:
            key: bytes | None = None
            if CONF_PASSWORD in user_input:
                key = hash_password(user_input[CONF_PASSWORD].encode())
            port: int | None = reauth_entry.data.get(CONF_PORT)
            try:
                mac = await self._test_connection(host, key, port)
            except OSError:
                errors[CONF_HOST] = self.ERROR_INVALID_HOST
            except Authenticator.Error:
                errors[CONF_PASSWORD] = self.ERROR_INVALID_AUTH
            else:
                data: dict[str, Any] = {CONF_HOST: host, CONF_MAC: mac}
                if port is not None:
                    data[CONF_PORT] = port
                if key is not None:
                    data[CONF_AUTHENTICATION] = key.hex()
                return self.async_update_reload_and_abort(
                    reauth_entry, data=data
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=voluptuous.Schema(
                {
                    voluptuous.Optional(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={"host": host},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()
        host: str = reconfigure_entry.data[CONF_HOST]

        if user_input is not None:
            new_host: str = user_input[CONF_HOST]
            key: bytes | None = None
            if CONF_PASSWORD in user_input:
                key = hash_password(user_input[CONF_PASSWORD].encode())
            elif CONF_AUTHENTICATION in reconfigure_entry.data:
                key = bytes.fromhex(reconfigure_entry.data[CONF_AUTHENTICATION])
            port: int | None = user_input.get(CONF_PORT)
            try:
                mac = await self._test_connection(new_host, key, port)
            except OSError:
                errors[CONF_HOST] = self.ERROR_INVALID_HOST
            except Authenticator.Error:
                errors[CONF_PASSWORD] = self.ERROR_INVALID_AUTH
            else:
                data: dict[str, Any] = {CONF_HOST: new_host, CONF_MAC: mac}
                if port is not None:
                    data[CONF_PORT] = port
                if key is not None:
                    data[CONF_AUTHENTICATION] = key.hex()
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data=data,
                    unique_id=new_host,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=voluptuous.Schema(
                {
                    voluptuous.Required(CONF_HOST, default=host): str,
                    voluptuous.Optional(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
