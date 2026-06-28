"""Sensor platform for CUKTECH GaN Charger."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CuktechChargerConfigEntry
from .const import DOMAIN, PORT_NAMES
from .coordinator import CuktechChargerCoordinator, PortData

_LOGGER = logging.getLogger(__name__)

PORT_KEYS = ["c1", "c2", "c3", "a"]

SENSOR_DEFINITIONS: list[dict[str, Any]] = []
for port_key in PORT_KEYS:
    port_name = PORT_NAMES[port_key]
    SENSOR_DEFINITIONS.extend([
        {
            "port_key": port_key,
            "attr": "voltage",
            "name": f"{port_name} Voltage",
            "unique_id_suffix": f"{port_key}_voltage",
            "device_class": SensorDeviceClass.VOLTAGE,
            "state_class": SensorStateClass.MEASUREMENT,
            "unit": UnitOfElectricPotential.VOLT,
            "icon": "mdi:sine-wave",
        },
        {
            "port_key": port_key,
            "attr": "current",
            "name": f"{port_name} Current",
            "unique_id_suffix": f"{port_key}_current",
            "device_class": SensorDeviceClass.CURRENT,
            "state_class": SensorStateClass.MEASUREMENT,
            "unit": UnitOfElectricCurrent.AMPERE,
            "icon": "mdi:current-ac",
        },
        {
            "port_key": port_key,
            "attr": "power",
            "name": f"{port_name} Power",
            "unique_id_suffix": f"{port_key}_power",
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "unit": UnitOfPower.WATT,
            "icon": "mdi:lightning-bolt",
        },
    ])


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CuktechChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for CUKTECH charger."""
    coordinator = entry.runtime_data
    entities: list[CuktechSensor] = []

    for sensor_def in SENSOR_DEFINITIONS:
        entities.append(
            CuktechSensor(coordinator, entry, sensor_def)
        )

    async_add_entities(entities)


class CuktechSensor(CoordinatorEntity[CuktechChargerCoordinator], SensorEntity):
    """Representation of a CUKTECH charger sensor."""

    def __init__(
        self,
        coordinator: CuktechChargerCoordinator,
        entry: CuktechChargerConfigEntry,
        sensor_def: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._port_key = sensor_def["port_key"]
        self._sensor_attr = sensor_def["attr"]
        self._attr_name = sensor_def["name"]
        self._attr_unique_id = f"{entry.entry_id}_{sensor_def['unique_id_suffix']}"
        self._attr_device_class = sensor_def["device_class"]
        self._attr_state_class = sensor_def["state_class"]
        self._attr_native_unit_of_measurement = sensor_def["unit"]
        self._attr_icon = sensor_def["icon"]
        self._attr_has_entity_name = True
        self._attr_translation_key = sensor_def["unique_id_suffix"].replace("-", "_")

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("mac", entry.entry_id).lower().replace(":", "_"))},
        }

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        port_data: PortData | None = self.coordinator.data.ports.get(self._port_key)
        if port_data is None:
            return None
        return getattr(port_data, self._sensor_attr, None)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        port_data = self.coordinator.data.ports.get(self._port_key)
        if port_data is None:
            return False
        return getattr(port_data, self._sensor_attr, None) is not None
