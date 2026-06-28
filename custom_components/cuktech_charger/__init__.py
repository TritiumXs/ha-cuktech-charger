"""Init for CUKTECH GaN Charger integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import CuktechChargerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
]

CuktechChargerConfigEntry = ConfigEntry[CuktechChargerCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: CuktechChargerConfigEntry
) -> bool:
    """Set up CUKTECH GaN Charger from a config entry."""
    mac: str = entry.data[CONF_ADDRESS]
    token: str = entry.data["token"]
    ble_key: str | None = entry.data.get("ble_key") or None

    coordinator = CuktechChargerCoordinator(
        hass=hass,
        mac=mac,
        token=token,
        ble_key=ble_key,
    )

    # Connect and auth on setup
    try:
        connected = await coordinator._connect_and_auth()
        if not connected:
            _LOGGER.warning(
                "Initial connection/auth failed for %s, will retry later", mac
            )
    except Exception as exc:
        _LOGGER.exception("Unexpected error during initial setup for %s: %s", mac, exc)

    # Do an initial data fetch
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Register the device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, mac.lower().replace(":", "_"))},
        name=entry.title,
        model="10 GaN Charger Ultra",
        manufacturer="CUKTECH",
        sw_version="",
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
    )

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(lambda: hass.async_create_task(coordinator.shutdown()))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CuktechChargerConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        await coordinator.shutdown()

    return unload_ok
