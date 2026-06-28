"""Switch platform for CUKTECH GaN Charger."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CuktechChargerConfigEntry
from .const import (
    DOMAIN,
    PIID_PORT_CONTROL,
    PIID_USB_A_ALWAYS_ON,
    PIID_IDLE_SCREEN_OFF,
    PIID_SCREEN_ORIENT_LOCK,
    PORT_BITS,
    PORT_NAMES,
)
from .coordinator import CuktechChargerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CuktechChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for CUKTECH charger."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []

    # Port switches (C1/C2/C3/A) - control PIID 16 bits
    for port_key in ["c1", "c2", "c3", "a"]:
        entities.append(
            PortSwitch(coordinator, entry, port_key)
        )

    # Feature switches (PIID 15, 19, 20)
    entities.append(
        FeatureSwitch(
            coordinator, entry,
            piid=PIID_USB_A_ALWAYS_ON,
            name="USB-A Always On",
            unique_id_suffix="usb_a_always_on",
            icon="mdi:usb-port",
        )
    )
    entities.append(
        FeatureSwitch(
            coordinator, entry,
            piid=PIID_IDLE_SCREEN_OFF,
            name="Idle Screen Off",
            unique_id_suffix="idle_screen_off",
            icon="mdi:monitor-off",
        )
    )
    entities.append(
        FeatureSwitch(
            coordinator, entry,
            piid=PIID_SCREEN_ORIENT_LOCK,
            name="Screen Orientation Lock",
            unique_id_suffix="screen_orient_lock",
            icon="mdi:lock",
        )
    )

    async_add_entities(entities)


class PortSwitch(CoordinatorEntity[CuktechChargerCoordinator], SwitchEntity):
    """Switch to control a single port on/off."""

    def __init__(
        self,
        coordinator: CuktechChargerCoordinator,
        entry: CuktechChargerConfigEntry,
        port_key: str,
    ) -> None:
        """Initialize port switch."""
        super().__init__(coordinator)
        self._port_key = port_key
        self._bit = PORT_BITS[port_key]
        port_name = PORT_NAMES[port_key]
        self._attr_name = f"{port_name} Port"
        self._attr_unique_id = f"{entry.entry_id}_{port_key}_port"
        self._attr_icon = "mdi:power-plug-outline"
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("mac", entry.entry_id).lower().replace(":", "_"))},
        }

    @property
    def is_on(self) -> bool | None:
        """Return if the port is on."""
        port_control = self.coordinator.data.port_control
        if port_control is None:
            return None
        return bool(port_control & (1 << self._bit))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the port on."""
        await self.coordinator.async_set_port_switch(self._port_key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the port off."""
        await self.coordinator.async_set_port_switch(self._port_key, False)


class FeatureSwitch(CoordinatorEntity[CuktechChargerCoordinator], SwitchEntity):
    """Switch to control a boolean feature (PIID 15, 19, 20)."""

    def __init__(
        self,
        coordinator: CuktechChargerCoordinator,
        entry: CuktechChargerConfigEntry,
        piid: int,
        name: str,
        unique_id_suffix: str,
        icon: str,
    ) -> None:
        """Initialize feature switch."""
        super().__init__(coordinator)
        self._piid = piid
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{unique_id_suffix}"
        self._attr_icon = icon
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("mac", entry.entry_id).lower().replace(":", "_"))},
        }

    @property
    def is_on(self) -> bool | None:
        """Return if the feature is on."""
        # pylint: disable=protected-access
        attr_map = {
            "usb_a_always_on": "usb_a_always_on",
            "idle_screen_off": "idle_screen_off",
            "screen_orient_lock": "screen_orient_lock",
        }
        for suffix, data_attr in attr_map.items():
            if self._attr_unique_id.endswith(suffix):
                val = getattr(self.coordinator.data, data_attr)
                if val is None:
                    return None
                return bool(val)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the feature on."""
        await self.coordinator.async_set_piid(self._piid, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the feature off."""
        await self.coordinator.async_set_piid(self._piid, 0)
