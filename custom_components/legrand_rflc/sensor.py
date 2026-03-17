"""The Legrand RFLC integration sensor platform."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Mapping
from typing import Any, Final

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, LegrandRFLCConfigEntry
from .hub import Hub

_LOGGER: Final = logging.getLogger(__name__)


class _HubSensor(SensorEntity):
    """Base sensor entity for the LC7001 hub device."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Hub, key: str, name: str) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.host()}:sensor:{key}"
        self._attr_translation_key = key
        self._attr_name = name

    @property
    def available(self) -> bool:
        return self._hub.connected and self._hub.authenticated

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._hub.host())})


class _ZoneCountSensor(_HubSensor):
    """Number of zones configured on the hub."""

    _attr_icon = "mdi:counter"

    def __init__(self, hub: Hub) -> None:
        super().__init__(hub, "zone_count", "Zone count")

    async def async_added_to_hass(self) -> None:
        hub = self._hub
        # Subscribe to the Service-level event so we catch responses
        # to ListZones requests (sent by async_setup_entry and on reconnect).
        hub.on(hub.EVENT_LIST_ZONES, self._on_list_zones)
        hub.on(hub.EVENT_ZONE_ADDED, self._on_zone_changed)
        hub.on(hub.EVENT_ZONE_DELETED, self._on_zone_changed)
        hub.on(hub.EVENT_DISCONNECTED, self._on_availability_changed)

    async def async_will_remove_from_hass(self) -> None:
        hub = self._hub

        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_LIST_ZONES, self._on_list_zones)
        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_ZONE_ADDED, self._on_zone_changed)
        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_ZONE_DELETED, self._on_zone_changed)
        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_DISCONNECTED, self._on_availability_changed)

    async def _on_availability_changed(self, *_args: object) -> None:
        self.async_write_ha_state()

    async def _on_zone_changed(self, *_args: object) -> None:
        # Zone added/deleted — request a fresh list. Response triggers
        # EVENT_LIST_ZONES which our _on_list_zones handles.
        await self._hub.send(self._hub.compose_list_zones())

    async def _on_list_zones(self, message: Mapping) -> None:
        try:
            self._hub.StatusError(message).raise_if()
        except self._hub.StatusError:
            return
        self._attr_native_value = len(
            message.get(self._hub.ZONE_LIST, [])
        )
        self.async_write_ha_state()


class _SystemPropertySensor(_HubSensor):
    """Sensor that reads a property from ReportSystemProperties."""

    def __init__(self, hub: Hub, key: str, name: str, prop_key: str) -> None:
        super().__init__(hub, key, name)
        self._prop_key = prop_key

    async def async_added_to_hass(self) -> None:
        hub = self._hub
        # Subscribe to BOTH the response event and the broadcast event.
        # EVENT_REPORT_SYSTEM_PROPERTIES fires for responses to our request.
        # EVENT_SYSTEM_PROPERTIES_CHANGED fires for hub-initiated broadcasts.
        hub.on(hub.EVENT_REPORT_SYSTEM_PROPERTIES, self._on_properties)
        hub.on(hub.EVENT_SYSTEM_PROPERTIES_CHANGED, self._on_properties)
        hub.on(hub.EVENT_DISCONNECTED, self._on_availability_changed)

    async def async_will_remove_from_hass(self) -> None:
        hub = self._hub

        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_REPORT_SYSTEM_PROPERTIES, self._on_properties)
        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_SYSTEM_PROPERTIES_CHANGED, self._on_properties)
        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_DISCONNECTED, self._on_availability_changed)

    async def _on_availability_changed(self, *_args: object) -> None:
        self.async_write_ha_state()

    async def _on_properties(self, message: Mapping) -> None:
        try:
            self._hub.StatusError(message).raise_if()
        except self._hub.StatusError:
            return
        props = message.get(self._hub.PROPERTY_LIST, {})
        if self._prop_key in props:
            self._attr_native_value = self._format(props[self._prop_key])
            self.async_write_ha_state()

    def _format(self, value: Any) -> Any:
        return value


class _TimeZoneSensor(_SystemPropertySensor):
    """Hub timezone offset sensor."""

    _attr_icon = "mdi:map-clock"

    def __init__(self, hub: Hub) -> None:
        super().__init__(hub, "time_zone", "Time zone", hub.EFFECTIVE_TIME_ZONE)

    def _format(self, value: Any) -> str:
        """Format seconds offset as ±HH:MM."""
        total = int(value)
        sign = "+" if total >= 0 else "-"
        total = abs(total)
        hours = total // 3600
        minutes = (total % 3600) // 60
        return f"UTC{sign}{hours:02d}:{minutes:02d}"


class _DSTSensor(_SystemPropertySensor):
    """Hub daylight saving time sensor."""

    _attr_icon = "mdi:weather-sunny-alert"

    def __init__(self, hub: Hub) -> None:
        super().__init__(
            hub, "daylight_saving_time", "Daylight saving time",
            hub.DAYLIGHT_SAVING_TIME,
        )

    def _format(self, value: Any) -> str:
        return "On" if value else "Off"


class _LocationSensor(_SystemPropertySensor):
    """Hub location info sensor."""

    _attr_icon = "mdi:map-marker"

    def __init__(self, hub: Hub) -> None:
        super().__init__(hub, "location", "Location", hub.LOCATION_INFO)


class _AddALightSensor(_SystemPropertySensor):
    """Hub add-a-light mode sensor."""

    _attr_icon = "mdi:lightbulb-plus"

    def __init__(self, hub: Hub) -> None:
        super().__init__(hub, "add_a_light", "Add a light mode", hub.ADD_A_LIGHT)

    def _format(self, value: Any) -> str:
        return "Active" if value else "Inactive"


class _BroadcastSensor(_HubSensor):
    """Sensor that reads a value from a periodic hub broadcast."""

    def __init__(
        self, hub: Hub, key: str, name: str, event: str, prop_key: str,
    ) -> None:
        super().__init__(hub, key, name)
        self._event = event
        self._prop_key = prop_key

    async def async_added_to_hass(self) -> None:
        hub = self._hub
        hub.on(self._event, self._on_broadcast)
        hub.on(hub.EVENT_DISCONNECTED, self._on_availability_changed)

    async def async_will_remove_from_hass(self) -> None:
        hub = self._hub

        with contextlib.suppress(ValueError):
            hub.off(self._event, self._on_broadcast)
        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_DISCONNECTED, self._on_availability_changed)

    async def _on_availability_changed(self, *_args: object) -> None:
        self.async_write_ha_state()

    async def _on_broadcast(self, message: Mapping) -> None:
        if self._prop_key in message:
            self._attr_native_value = self._format(message[self._prop_key])
            self.async_write_ha_state()

    def _format(self, value: Any) -> Any:
        return value


class _FirmwareVersionSensor(_BroadcastSensor):
    """Hub firmware version from BroadcastDiagnostics."""

    _attr_icon = "mdi:chip"

    def __init__(self, hub: Hub) -> None:
        super().__init__(
            hub, "firmware_version", "Firmware version",
            f"{hub.SERVICE}:BroadcastDiagnostics", "FirmwareVersion",
        )


class _FreeMemorySensor(_BroadcastSensor):
    """Hub free memory from BroadcastMemory."""

    _attr_icon = "mdi:memory"
    _attr_native_unit_of_measurement = "B"

    def __init__(self, hub: Hub) -> None:
        super().__init__(
            hub, "free_memory", "Free memory",
            f"{hub.SERVICE}:BroadcastMemory", "FreeMemory:",
        )


class _ConnectedClientsSensor(_BroadcastSensor):
    """Number of JSON/TCP clients connected to the hub."""

    _attr_icon = "mdi:lan-connect"

    def __init__(self, hub: Hub) -> None:
        super().__init__(
            hub, "connected_clients", "Connected clients",
            f"{hub.SERVICE}:BroadcastMemory", "JsonConnections:",
        )


class _AuthExemptSensor(_BroadcastSensor):
    """Whether the hub is in password-exempt mode."""

    _attr_icon = "mdi:shield-lock-open-outline"

    def __init__(self, hub: Hub) -> None:
        super().__init__(
            hub, "auth_exempt", "Password exempt",
            f"{hub.SERVICE}:BroadcastDiagnostics", "AuthExempt",
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LegrandRFLCConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up the Legrand RFLC sensor platform."""
    hub = entry.runtime_data.hub

    entities: list[SensorEntity] = [
        _ZoneCountSensor(hub),
        _TimeZoneSensor(hub),
        _DSTSensor(hub),
        _LocationSensor(hub),
        _AddALightSensor(hub),
        _FirmwareVersionSensor(hub),
        _FreeMemorySensor(hub),
        _ConnectedClientsSensor(hub),
        _AuthExemptSensor(hub),
    ]
    async_add_entities(entities, False)

    async def _request_initial_data(*_args: object) -> None:
        """Send data requests on (re)authentication."""
        await hub.send(hub.compose_report_system_properties())
        await hub.send(hub.compose_list_zones())

    hub.on(hub.EVENT_AUTHENTICATED, _request_initial_data)

    # Send initial requests now — entities are subscribed, and the hub loop
    # will deliver the responses via Service-level events.
    await hub.send(hub.compose_report_system_properties())
    await hub.send(hub.compose_list_zones())
