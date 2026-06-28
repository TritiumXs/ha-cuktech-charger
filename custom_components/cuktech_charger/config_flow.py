"""Config flow for CUKTECH GaN Charger integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from ._ble import CuktechBLEController, require_runtime_dependencies

_LOGGER = logging.getLogger(__name__)

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required("token", description={"suggested_value": ""}): cv.string,
        vol.Optional("ble_key", description={"suggested_value": ""}): cv.string,
    }
)

MANUAL_MAC_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADDRESS, description={"suggested_value": ""}): cv.string,
    }
)


async def _validate_auth(
    mac: str, token: str, ble_key: str | None
) -> dict[str, str]:
    """Validate authentication. Returns errors dict or empty."""
    errors: dict[str, str] = {}

    try:
        token_bytes = bytes.fromhex(token)
    except ValueError:
        errors["token"] = "invalid_token_format"
        return errors
    if len(token_bytes) != 12:
        errors["token"] = "invalid_token_length"
        return errors

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
        _LOGGER.exception("Auth error for %s: %s", mac, exc)
        errors["base"] = "unknown"
    finally:
        await ctrl.disconnect()

    return errors


def _is_cuktech_device(name: str | None) -> bool:
    """Return True if the BLE device name matches the known CUKTECH pattern.

    CUKTECH chargers broadcast a name like ``njcuk.fitting.ad1204``.
    Matching on ``"njcuk"`` (case-insensitive) is used by the original
    cuktech-ble-controller project and is more reliable than UUID matching.
    """
    return bool(name and "njcuk" in name.lower())
    return discovery_info.name or "CUKTECH Charger"


class CuktechChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CUKTECH GaN Charger."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfo | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfo] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> FlowResult:
        """Handle bluetooth discovery - triggered by HA when a 0xFE95 device is found."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        name = _name_from_discovery(discovery_info)
        self.context["title_placeholders"] = {"name": name}

        return await self.async_step_token()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual user start - scan first, then pick device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]

            # User chose manual entry
            if address == "__manual__":
                return await self.async_step_manual()

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._discovery_info = self._discovered_devices[address]
            self.context["title_placeholders"] = {
                "name": _name_from_discovery(self._discovery_info),
                "address": self._discovery_info.address,
            }
            return await self.async_step_token()

        # ── Scan for nearby CUKTECH chargers ──────────────────────────
        self._discovered_devices = {}

        # 1) Try HA Bluetooth integration cache (fast, no active scan)
        try:
            service_infos = async_discovered_service_info(self.hass)
            for info in service_infos:
                name: str | None = getattr(info, "name", None)
                if _is_cuktech_device(name):
                    self._discovered_devices[info.address] = info

            if self._discovered_devices:
                _LOGGER.info(
                    "Found %d CUKTECH charger(s) via HA Bluetooth cache",
                    len(self._discovered_devices),
                )
            else:
                _LOGGER.info(
                    "HA Bluetooth cache had %d total device(s), no CUKTECH (njcuk) name",
                    len(service_infos),
                )
        except Exception as exc:
            _LOGGER.warning("Could not query HA Bluetooth cache: %s", exc)

        # 2) Fall back to an active BLE scan (needed when HA cache is empty)
        if not self._discovered_devices:
            try:
                from bleak import BleakScanner

                _LOGGER.info("Starting active BLE scan (10 s timeout) …")
                results = await BleakScanner.discover(timeout=10, return_adv=True)
                _LOGGER.info("BLE scan finished: %d device(s) seen", len(results))

                for mac, (device, adv) in results.items():
                    if adv is None:
                        continue
                    name = getattr(adv, "local_name", None) or getattr(
                        device, "name", None
                    )
                    if _is_cuktech_device(name):
                        self._discovered_devices[mac] = BluetoothServiceInfo(
                            name=name or "CUKTECH Charger",
                            address=mac,
                            rssi=getattr(adv, "rssi", 0) or 0,
                            manufacturer_data=getattr(adv, "manufacturer_data", {}) or {},
                            service_data=getattr(adv, "service_data", {}) or {},
                            service_uuids=getattr(adv, "service_uuids", []) or [],
                            source="local",
                        )

                if self._discovered_devices:
                    _LOGGER.info(
                        "Found %d CUKTECH charger(s) via active BLE scan",
                        len(self._discovered_devices),
                    )
                else:
                    _LOGGER.warning(
                        "Active BLE scan saw %d device(s), no CUKTECH (njcuk) name",
                        len(results),
                    )
            except Exception as exc:
                _LOGGER.warning("Active BLE scan failed: %s", exc)

        if not self._discovered_devices:
            _LOGGER.warning(
                "No CUKTECH charger found – falling back to manual MAC entry"
            )
            return await self.async_step_manual()

        # Build selection: discovered devices + manual entry option
        selection: dict[str, str] = {
            mac: f"{_name_from_discovery(info)} ({mac})"
            for mac, info in sorted(self._discovered_devices.items())
        }
        selection["__manual__"] = "▶ Enter MAC address manually…"

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(selection),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual MAC address entry (fallback when scan finds nothing)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = user_input[CONF_ADDRESS].strip().upper()
            # Basic MAC validation
            parts = mac.split(":")
            if len(parts) != 6 or not all(
                len(p) == 2 and all(c in "0123456789ABCDEF" for c in p)
                for p in parts
            ):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(mac, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                # Create synthetic discovery info for the manually entered MAC
                self._discovery_info = BluetoothServiceInfo(
                    name=f"CUKTECH Charger ({mac})",
                    address=mac,
                    rssi=0,
                    manufacturer_data={},
                    service_data={},
                    service_uuids=["0000fe95-0000-1000-8000-00805f9b34fb"],
                    source="manual",
                )
                self.context["title_placeholders"] = {
                    "name": self._discovery_info.name,
                    "address": mac,
                }
                return await self.async_step_token()

        return self.async_show_form(
            step_id="manual",
            data_schema=MANUAL_MAC_SCHEMA,
            errors=errors,
            description_placeholders={},
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle token input step."""
        assert self._discovery_info

        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input["token"]
            ble_key = user_input.get("ble_key") or None

            # Validate by connecting
            errs = await _validate_auth(
                self._discovery_info.address, token, ble_key
            )
            if not errs:
                return self.async_create_entry(
                    title=_name_from_discovery(self._discovery_info),
                    data={
                        CONF_ADDRESS: self._discovery_info.address,
                        "token": token,
                        "ble_key": ble_key or "",
                    },
                )
            errors = errs

        return self.async_show_form(
            step_id="token",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={
                "name": _name_from_discovery(self._discovery_info),
                "address": self._discovery_info.address,
            },
        )
