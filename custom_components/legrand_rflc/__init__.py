"""The Legrand RFLC integration.

https://www.legrand.us/solutions/smart-lighting/radio-frequency-lighting-controls
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Final

from homeassistant.const import CONF_AUTHENTICATION, CONF_HOST, CONF_MAC, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, LegrandRFLCConfigEntry, LegrandRFLCData
from .hub import Authenticator, Connector, Hub

_LOGGER: Final = logging.getLogger(__name__)

PLATFORMS: Final[list[str]] = ["light", "sensor"]


async def async_setup_entry(
    hass: HomeAssistant, entry: LegrandRFLCConfigEntry
) -> bool:
    """Set up Legrand LC7001 from a config entry."""
    data = entry.data
    host: str = data[CONF_HOST]
    kwargs: dict[str, object] = {}
    if CONF_AUTHENTICATION in data:
        kwargs["key"] = bytes.fromhex(data[CONF_AUTHENTICATION])
    if CONF_PORT in data:  # for testing only (server emulation on localhost)
        kwargs["port"] = data[CONF_PORT]

    # Test connection before setting up the persistent hub.
    test = Connector(host, loop_timeout=-1, **kwargs)
    try:
        await test.loop()
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to LC7001 hub at {host}"
        ) from err
    except Authenticator.Error as err:
        entry.async_start_reauth(hass)
        raise ConfigEntryNotReady(
            f"Authentication failed for LC7001 hub at {host}"
        ) from err

    hub = Hub(host, **kwargs)
    entry.runtime_data = LegrandRFLCData(hub=hub)

    # Register the hub device.
    mac_raw: str = data.get(CONF_MAC, "")
    mac_formatted = dr.format_mac(mac_raw) if mac_raw else ""
    device_registry = dr.async_get(hass)
    hub_device_kwargs: dict[str, object] = {
        "config_entry_id": entry.entry_id,
        "identifiers": {(DOMAIN, host)},
        "manufacturer": "Legrand",
        "name": "Whole House Lighting Controller",
        "model": "LC7001",
    }
    if mac_formatted:
        hub_device_kwargs["connections"] = {
            (dr.CONNECTION_NETWORK_MAC, mac_formatted)
        }
    hub_device = device_registry.async_get_or_create(**hub_device_kwargs)

    # Clean up stale connection entries (e.g. IP was incorrectly stored as MAC
    # in older versions). Keep only the valid formatted MAC.
    stale = {
        (t, v)
        for t, v in hub_device.connections
        if t == dr.CONNECTION_NETWORK_MAC and v != mac_formatted
    }
    if stale:
        device_registry.async_update_device(
            hub_device.id,
            new_connections={
                c for c in hub_device.connections if c not in stale
            },
        )

    platforms_setup = False

    async def on_authenticated(*_args: object) -> None:
        nonlocal platforms_setup
        if not platforms_setup:
            platforms_setup = True
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def on_unauthenticated(*_args: object) -> None:
        entry.async_start_reauth(hass)

    async def on_zone_changed(message: Mapping) -> None:
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    # Use persistent hub.on() — NOT hub.once().
    # hub.once() caused a critical bug: after the first disconnect/reconnect
    # cycle, the handlers were gone and HA could never recover.
    hub.on(hub.EVENT_AUTHENTICATED, on_authenticated)
    hub.on(hub.EVENT_UNAUTHENTICATED, on_unauthenticated)
    hub.on(hub.EVENT_ZONE_ADDED, on_zone_changed)
    hub.on(hub.EVENT_ZONE_DELETED, on_zone_changed)

    asyncio.create_task(hub.loop())  # not hass.async_create_task

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: LegrandRFLCConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removal of a device if it is not the hub itself."""
    # Protect the hub device; allow removal of orphaned zone devices.
    hub = entry.runtime_data.hub
    return (DOMAIN, hub.host()) not in device_entry.identifiers


async def async_unload_entry(
    hass: HomeAssistant, entry: LegrandRFLCConfigEntry
) -> bool:
    """Unload a config entry."""
    hub = entry.runtime_data.hub
    await hub.cancel()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
