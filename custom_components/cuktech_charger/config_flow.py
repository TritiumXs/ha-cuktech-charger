"""Config flow for CUKTECH GaN Charger integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_MAC, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.components.bluetooth import (
    async_discovered_service_info,
    async_get_scanner,
    BluetoothServiceInfoBleak,
)

from .const import DOMAIN
from ._ble import UUID_FE95, CuktechBLEController, require_runtime_dependencies

_LOGGER = logging.getLogger(__name__)

STEP_AUTH_SCHEMA = vol.Schema(
    {
        vol.Required("token", description={"suggested_value": ""}): cv.string,
        vol.Optional("ble_key", description={"suggested_value": ""}): cv.string,
    }
)


async def _validate_auth(
    hass: HomeAssistant, mac: str, token: str, ble_key: str | None
) -> dict[str, str]:
    """Validate authentication by connecting to the device.

    Returns a dict with errors on failure, or empty dict on success.
    """
    errors: dict[str, str] = {}

    # Validate token is 12-byte hex
    try:
        token_bytes = bytes.fromhex(token)
    except ValueError:
        errors["token"] = "invalid_token_format"
        return errors
    if len(token_bytes) != 12:
        errors["token"] = "invalid_token_length"
        return errors

    # Validate optional BLE key is 16-byte hex
    key_bytes: bytes | None = None
    if ble_key:
        try:
            key_bytes = bytes.fromhex(ble_key)
        except ValueError:
            errors["ble_key"] = "invalid_key_format"
            return errors
        if len(key_bytes) != 16:
            errors["ble_key"] = "invalid_key_length"
            return errors

    try:
        require_runtime_dependencies()
    except RuntimeError as exc:
        _LOGGER.error("Missing runtime dependencies: %s", exc)
        errors["base"] = "missing_deps"
        return errors

    # Attempt connection and auth
    ctrl = CuktechBLEController(mac=mac, token=token_bytes)
    try:
        connected = await ctrl.connect()
        if not connected:
            errors["base"] = "cannot_connect"
            return errors

        auth_ok = await ctrl.authenticate()
        if not auth_ok:
            errors["base"] = "auth_failed"
            return errors
    except Exception as exc:
        _LOGGER.exception("Connection/auth error for %s: %s", mac, exc)
        errors["base"] = "unknown"
    finally:
        await ctrl.disconnect()

    return errors


async def _scan_for_devices(hass: HomeAssistant) -> list[BluetoothServiceInfoBleak]:
    """Scan for CUKTECH chargers using BLE."""
    devices: list[BluetoothServiceInfoBleak] = []

    # Try HA's built-in bluetooth integration first
    for service_info in async_discovered_service_info(hass, connectable=True):
        if UUID_FE95 in service_info.service_uuids:
            devices.append(service_info)

    if devices:
        return devices

    # Fallback: use BleakScanner directly
    try:
        from bleak import BleakScanner

        scanner = async_get_scanner(hass)
        if scanner:
            scanned = await scanner.discover(timeout=10)
            for device in scanned:
                if device.advertisement_data and UUID_FE95 in device.advertisement_data.service_uuids:
                    # Wrap as simple service info
                    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
                    from bleak.backends.device import BLEDevice
                    # We have a list of BLEDevice, wrap it
                    pass
    except Exception:
        pass

    return devices


class CuktechChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CUKTECH GaN Charger."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._token: str = ""
        self._ble_key: str | None = None
        self._discovered_devices: dict[str, str] = {}  # MAC -> name

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - enter auth credentials."""
        if user_input is not None:
            self._token = user_input["token"]
            self._ble_key = user_input.get("ble_key") or None
            return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_AUTH_SCHEMA,
            description_placeholders={},
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the device selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = user_input[CONF_MAC]
            # Validate auth
            errs = await _validate_auth(
                self.hass, mac, self._token, self._ble_key
            )
            if not errs:
                await self.async_set_unique_id(mac.lower().replace(":", "_"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._discovered_devices.get(mac, mac),
                    data={
                        CONF_MAC: mac,
                        CONF_TOKEN: self._token,
                        "ble_key": self._ble_key or "",
                    },
                )
            errors = errs

        # Scan for devices
        try:
            discovered = await _scan_for_devices(self.hass)
        except Exception as exc:
            _LOGGER.exception("Scan failed: %s", exc)
            discovered = []

        # Also try direct BleakScanner
        if not discovered:
            try:
                from bleak import BleakScanner

                scanner = BleakScanner()
                ble_devices = await scanner.discover(timeout=10, return_adv=True)
                for mac, (device, adv) in ble_devices.items():
                    service_uuids = adv.service_uuids if adv else []
                    if UUID_FE95 in service_uuids:
                        name = adv.local_name or device.name or "CUKTECH Charger"
                        self._discovered_devices[mac] = name
            except Exception as exc:
                _LOGGER.warning("Direct BLE scan failed: %s", exc)
                errors["base"] = "scan_failed"

        if not self._discovered_devices:
            # No devices found; allow manual MAC entry
            return await self.async_step_manual()

        schema = vol.Schema(
            {
                vol.Required(CONF_MAC): vol.In(
                    {mac: f"{name} ({mac})" for mac, name in self._discovered_devices.items()}
                ),
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual MAC entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = user_input[CONF_MAC].strip().upper()
            # Basic MAC validation
            parts = mac.split(":")
            if len(parts) != 6 or not all(
                len(p) == 2 and all(c in "0123456789ABCDEF" for c in p) for p in parts
            ):
                errors[CONF_MAC] = "invalid_mac"
            else:
                errs = await _validate_auth(
                    self.hass, mac, self._token, self._ble_key
                )
                if not errs:
                    await self.async_set_unique_id(mac.lower().replace(":", "_"))
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"CUKTECH Charger ({mac})",
                        data={
                            CONF_MAC: mac,
                            CONF_TOKEN: self._token,
                            "ble_key": self._ble_key or "",
                        },
                    )
                errors = errs

        schema = vol.Schema(
            {
                vol.Required(CONF_MAC): cv.string,
            }
        )

        return self.async_show_form(
            step_id="manual",
            data_schema=schema,
            errors=errors,
            description_placeholders={},
        )
