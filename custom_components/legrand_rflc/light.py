"""The Legrand RFLC integration light platform."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from typing import Any, Final

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, LegrandRFLCConfigEntry
from .hub import Hub

_LOGGER: Final = logging.getLogger(__name__)

PARALLEL_UPDATES: Final = 1


class _Switch(LightEntity):
    _attr_should_poll = False
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "switch"

    def __init__(self, hub: Hub, zid: int, properties: Mapping) -> None:
        self._hub = hub
        self._zid = zid
        self._zone_name: str = properties[hub.NAME]
        self._attr_is_on: bool = properties[hub.POWER]
        self._device_type: str = properties[hub.DEVICE_TYPE]
        self._attr_unique_id = f"{hub.host()}:{zid}"
        self._was_available: bool | None = None

    @property
    def available(self) -> bool:
        """Return True if the hub is connected and authenticated."""
        return self._hub.connected and self._hub.authenticated

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this zone."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="Legrand",
            model="LC7001",
            name=self._zone_name,
            via_device=(DOMAIN, self._hub.host()),
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to hub events when entity is added."""
        hub = self._hub
        zid = self._zid
        hub.on(
            f"{hub.EVENT_ZONE_PROPERTIES_CHANGED}:{zid}",
            self._zone_properties_changed,
        )
        hub.on(hub.EVENT_CONNECTED, self._on_availability_changed)
        hub.on(hub.EVENT_DISCONNECTED, self._on_availability_changed)
        hub.on(hub.EVENT_AUTHENTICATED, self._on_authenticated)
        hub.on(hub.EVENT_UNAUTHENTICATED, self._on_availability_changed)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from hub events when entity is removed."""
        hub = self._hub
        zid = self._zid
        with contextlib.suppress(ValueError):
            hub.off(
                f"{hub.EVENT_ZONE_PROPERTIES_CHANGED}:{zid}",
                self._zone_properties_changed,
            )
        for event in (
            hub.EVENT_CONNECTED,
            hub.EVENT_DISCONNECTED,
            hub.EVENT_UNAUTHENTICATED,
        ):
            with contextlib.suppress(ValueError):
                hub.off(event, self._on_availability_changed)
        with contextlib.suppress(ValueError):
            hub.off(hub.EVENT_AUTHENTICATED, self._on_authenticated)

    def _log_availability(self) -> None:
        """Log availability transitions (once per direction)."""
        now_available = self.available
        if self._was_available is not None and self._was_available != now_available:
            if now_available:
                _LOGGER.info("%s is available", self.entity_id)
            else:
                _LOGGER.warning("%s is unavailable", self.entity_id)
        self._was_available = now_available

    async def _on_availability_changed(self, *_args: object) -> None:
        """Handle hub connection/auth state changes."""
        self._log_availability()
        self.async_write_ha_state()

    async def _on_authenticated(self, *_args: object) -> None:
        """Handle (re)authentication — refresh zone state from hub."""
        self._log_availability()

        # Re-query zone properties to catch changes during disconnection.
        result: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def handle_report(message: Mapping) -> None:
            try:
                self._hub.StatusError(message).raise_if()
            except self._hub.StatusError:
                if not result.done():
                    result.set_result(None)
                return
            self._apply_properties(message)
            self.async_write_ha_state()
            if not result.done():
                result.set_result(None)

        await self._hub.handle_send(
            handle_report,
            self._hub.compose_report_zone_properties(self._zid),
        )
        try:
            await asyncio.wait_for(result, timeout=5.0)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "%s: timeout refreshing state after reconnection",
                self.entity_id,
            )

    def _apply_properties(self, message: Mapping) -> None:
        """Apply zone properties from a hub message."""
        hub = self._hub
        if hub.PROPERTY_LIST in message:
            properties = message[hub.PROPERTY_LIST]
            if hub.POWER in properties:
                self._attr_is_on = properties[hub.POWER]

    async def _zone_properties_changed(self, message: Mapping) -> None:
        """Handle zone property change events from the hub."""
        self._apply_properties(message)
        self.async_write_ha_state()

    async def _async_switch(self, power: bool) -> None:
        """Send on/off command and await hub response."""
        hub = self._hub
        result: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def handle(message: Mapping) -> None:
            error = hub.StatusError(message)
            if error:
                if not result.done():
                    result.set_exception(
                        HomeAssistantError(
                            translation_domain=DOMAIN,
                            translation_key="switch_failed",
                            translation_placeholders={
                                "entity": self.entity_id or "",
                                "error": str(error.args[2] or "hub error"),
                            },
                        )
                    )
            elif not result.done():
                result.set_result(None)

        await hub.handle_send(
            handle, hub.compose_set_zone_properties(self._zid, power=power)
        )
        await result

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        await self._async_switch(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self._async_switch(False)


class _Dimmer(_Switch):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_translation_key = "dimmer"

    @staticmethod
    def _normalize(value: int, ceiling: int) -> float:
        """Normalize [0, ceiling] to [0.0, 1.0]."""
        return value / ceiling

    @staticmethod
    def _quantize(value: float, ceiling: int) -> int:
        """Quantize [0.0, 1.0] to [0, ceiling]."""
        return int(value * ceiling)

    # Brightness ceilings for Home Assistant and LC7001.
    HA: Final[int] = 255
    US: Final[int] = 100

    @staticmethod
    def _to_ha(value: int) -> int:
        return _Dimmer._quantize(_Dimmer._normalize(value, _Dimmer.US), _Dimmer.HA)

    @staticmethod
    def _from_ha(value: int) -> int:
        return _Dimmer._quantize(_Dimmer._normalize(value, _Dimmer.HA), _Dimmer.US)

    def __init__(self, hub: Hub, zid: int, properties: Mapping) -> None:
        super().__init__(hub, zid, properties)
        self._attr_brightness: int = self._to_ha(properties[hub.POWER_LEVEL])

    def _apply_properties(self, message: Mapping) -> None:
        """Apply zone properties including brightness."""
        super()._apply_properties(message)
        hub = self._hub
        if hub.PROPERTY_LIST in message:
            properties = message[hub.PROPERTY_LIST]
            if hub.POWER_LEVEL in properties:
                self._attr_brightness = self._to_ha(properties[hub.POWER_LEVEL])

    async def _async_dimmer(self, power: bool, **kwargs: Any) -> None:
        """Send dimmer command and await hub response."""
        hub = self._hub
        result: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def handle(message: Mapping) -> None:
            error = hub.StatusError(message)
            if error:
                if not result.done():
                    result.set_exception(
                        HomeAssistantError(
                            translation_domain=DOMAIN,
                            translation_key="dimmer_failed",
                            translation_placeholders={
                                "entity": self.entity_id or "",
                                "error": str(error.args[2] or "hub error"),
                            },
                        )
                    )
            elif not result.done():
                result.set_result(None)

        properties: dict[str, object] = {"power": power}
        if ATTR_BRIGHTNESS in kwargs:
            brightness = self._from_ha(kwargs[ATTR_BRIGHTNESS])
            properties["power_level"] = brightness
        else:
            brightness = self._from_ha(self.brightness) if power else 0
        if ATTR_TRANSITION in kwargs:
            change = abs(brightness - self._from_ha(self.brightness))
            properties["ramp_rate"] = min(
                max(int(change / kwargs[ATTR_TRANSITION]), 1), 100
            )
        await hub.handle_send(
            handle,
            hub.compose_set_zone_properties(self._zid, **properties),
        )
        await result

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the dimmer."""
        await self._async_dimmer(True, **kwargs)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the dimmer."""
        await self._async_dimmer(False, **kwargs)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LegrandRFLCConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up the Legrand RFLC integration light platform."""
    hub = entry.runtime_data.hub

    async def zones(message: Mapping) -> None:
        async def zone(message: Mapping) -> None:
            zid: int = message[hub.ZID]
            properties = message[hub.PROPERTY_LIST]
            device_type: str = properties[hub.DEVICE_TYPE]
            if device_type == hub.DIMMER:
                async_add_entities([_Dimmer(hub, zid, properties)], False)
            elif device_type == hub.SWITCH:
                async_add_entities([_Switch(hub, zid, properties)], False)

        hub.StatusError(message).raise_if()
        for item in message[hub.ZONE_LIST]:
            await hub.handle_send(
                zone, hub.compose_report_zone_properties(item[hub.ZID])
            )

    await hub.handle_send(zones, hub.compose_list_zones())
