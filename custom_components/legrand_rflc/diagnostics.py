"""Diagnostics support for the Legrand RFLC integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any, Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_AUTHENTICATION
from homeassistant.core import HomeAssistant

from .const import LegrandRFLCConfigEntry

_LOGGER: Final = logging.getLogger(__name__)

TO_REDACT: Final = {CONF_AUTHENTICATION}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: LegrandRFLCConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    hub = entry.runtime_data.hub

    diag: dict[str, Any] = {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "hub": {
            "host": hub.host(),
            "connected": hub.connected,
            "authenticated": hub.authenticated,
        },
    }

    if not (hub.connected and hub.authenticated):
        return diag

    # Query zone list from the hub.
    zone_list_future: asyncio.Future[list[Mapping]] = (
        asyncio.get_running_loop().create_future()
    )

    async def handle_zones(message: Mapping) -> None:
        try:
            hub.StatusError(message).raise_if()
        except hub.StatusError:
            if not zone_list_future.done():
                zone_list_future.set_result([])
            return
        if not zone_list_future.done():
            zone_list_future.set_result(message.get(hub.ZONE_LIST, []))

    await hub.handle_send(handle_zones, hub.compose_list_zones())

    try:
        zone_items = await asyncio.wait_for(zone_list_future, timeout=5.0)
    except asyncio.TimeoutError:
        _LOGGER.warning("Timeout querying zone list for diagnostics")
        return diag

    # Query each zone's properties.
    zones: list[dict[str, Any]] = []
    for item in zone_items:
        zid: int = item[hub.ZID]
        zone_future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )

        async def handle_zone(
            msg: Mapping, _future: asyncio.Future[dict[str, Any]] = zone_future
        ) -> None:
            try:
                hub.StatusError(msg).raise_if()
            except hub.StatusError:
                if not _future.done():
                    _future.set_result({})
                return
            if not _future.done():
                _future.set_result(dict(msg.get(hub.PROPERTY_LIST, {})))

        await hub.handle_send(
            handle_zone, hub.compose_report_zone_properties(zid)
        )

        try:
            props = await asyncio.wait_for(zone_future, timeout=5.0)
        except asyncio.TimeoutError:
            props = {}

        zones.append({"zid": zid, "properties": props})

    diag["zones"] = zones
    return diag
