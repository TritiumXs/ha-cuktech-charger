"""Select platform for CUKTECH GaN Charger."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CuktechChargerConfigEntry
from .const import (
    DOMAIN,
    PIID_SCENE_MODE,
    PIID_SCREEN_TIMEOUT,
    PIID_LANGUAGE,
    OPTIONS_SCENE_MODE,
    OPTIONS_SCREEN_TIMEOUT,
    OPTIONS_LANGUAGE,
    SCENE_MODE_REVERSE_MAP,
    SCREEN_TIMEOUT_REVERSE_MAP,
    LANGUAGE_REVERSE_MAP,
)
from .coordinator import CuktechChargerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CuktechChargerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for CUKTECH charger."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        SceneModeSelect(coordinator, entry),
        ScreenTimeoutSelect(coordinator, entry),
        LanguageSelect(coordinator, entry),
    ]

    async_add_entities(entities)


class SceneModeSelect(CoordinatorEntity[CuktechChargerCoordinator], SelectEntity):
    """Select for scene mode (PIID 5)."""

    def __init__(
        self,
        coordinator: CuktechChargerCoordinator,
        entry: CuktechChargerConfigEntry,
    ) -> None:
        """Initialize scene mode select."""
        super().__init__(coordinator)
        self._attr_name = "Scene Mode"
        self._attr_unique_id = f"{entry.entry_id}_scene_mode"
        self._attr_options = OPTIONS_SCENE_MODE
        self._attr_icon = "mdi:state-machine"
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("mac", entry.entry_id).lower().replace(":", "_"))},
        }

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        val = self.coordinator.data.scene_mode
        if val is None:
            return None
        from .const import SCENE_MODE_VALUE_MAP
        return SCENE_MODE_VALUE_MAP.get(val)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        value = SCENE_MODE_REVERSE_MAP.get(option)
        if value is None:
            _LOGGER.error("Invalid scene mode option: %s", option)
            return
        await self.coordinator.async_set_piid(PIID_SCENE_MODE, value)


class ScreenTimeoutSelect(CoordinatorEntity[CuktechChargerCoordinator], SelectEntity):
    """Select for screen timeout (PIID 6)."""

    def __init__(
        self,
        coordinator: CuktechChargerCoordinator,
        entry: CuktechChargerConfigEntry,
    ) -> None:
        """Initialize screen timeout select."""
        super().__init__(coordinator)
        self._attr_name = "Screen Timeout"
        self._attr_unique_id = f"{entry.entry_id}_screen_timeout"
        self._attr_options = OPTIONS_SCREEN_TIMEOUT
        self._attr_icon = "mdi:timer-outline"
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("mac", entry.entry_id).lower().replace(":", "_"))},
        }

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        val = self.coordinator.data.screen_timeout
        if val is None:
            return None
        from .const import SCREEN_TIMEOUT_VALUE_MAP
        return SCREEN_TIMEOUT_VALUE_MAP.get(val)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        value = SCREEN_TIMEOUT_REVERSE_MAP.get(option)
        if value is None:
            _LOGGER.error("Invalid screen timeout option: %s", option)
            return
        await self.coordinator.async_set_piid(PIID_SCREEN_TIMEOUT, value)


class LanguageSelect(CoordinatorEntity[CuktechChargerCoordinator], SelectEntity):
    """Select for language (PIID 13)."""

    def __init__(
        self,
        coordinator: CuktechChargerCoordinator,
        entry: CuktechChargerConfigEntry,
    ) -> None:
        """Initialize language select."""
        super().__init__(coordinator)
        self._attr_name = "Language"
        self._attr_unique_id = f"{entry.entry_id}_language"
        self._attr_options = OPTIONS_LANGUAGE
        self._attr_icon = "mdi:translate"
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data.get("mac", entry.entry_id).lower().replace(":", "_"))},
        }

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        val = self.coordinator.data.language
        if val is None:
            return None
        from .const import LANGUAGE_VALUE_MAP
        return LANGUAGE_VALUE_MAP.get(val)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        value = LANGUAGE_REVERSE_MAP.get(option)
        if value is None:
            _LOGGER.error("Invalid language option: %s", option)
            return
        await self.coordinator.async_set_piid(PIID_LANGUAGE, value)
