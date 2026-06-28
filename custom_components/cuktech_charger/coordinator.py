"""Coordinator for CUKTECH GaN Charger integration."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import CONF_MAC, CONF_TOKEN

from ._ble import (
    CuktechBLEController,
    SIID_CHARGER,
    PORT_BITS,
    HANDLE_CMD_RECV,
    CHAR_CMD_RECV,
)
from .const import (
    DOMAIN,
    PIID_PORT_CONTROL,
    PIID_SCENE_MODE,
    PIID_SCREEN_TIMEOUT,
    PIID_LANGUAGE,
    PIID_USB_A_ALWAYS_ON,
    PIID_IDLE_SCREEN_OFF,
    PIID_SCREEN_ORIENT_LOCK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_RECONNECT_DELAY,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PortData:
    """Data for a single port."""

    voltage: float | None = None
    current: float | None = None
    power: float | None = None


@dataclass
class ChargerState:
    """Full charger state snapshot."""

    ports: dict[str, PortData] = field(default_factory=lambda: {
        "c1": PortData(),
        "c2": PortData(),
        "c3": PortData(),
        "a": PortData(),
    })
    scene_mode: int | None = None
    screen_timeout: int | None = None
    language: int | None = None
    port_control: int | None = None  # PIID 16 bitmask
    usb_a_always_on: int | None = None
    idle_screen_off: int | None = None
    screen_orient_lock: int | None = None


def _decode_port_push(pt: bytes, piid: int) -> dict[str, float] | None:
    """Parse port push data from encrypted payload.

    Format: b4=0x04, piid in pt[7], value bytes at pt[11:15] or pt[10:14].
    The 4 bytes encode: voltage_hi, voltage_lo, current_hi, current_lo
    with scaling: 0.001 per unit.
    """
    if len(pt) >= 15:
        raw = pt[11:15]
    elif len(pt) >= 13:
        raw = pt[10:14]
    else:
        return None

    if len(raw) < 4:
        return None

    hi16 = (raw[0] << 8) | raw[1]
    lo16 = (raw[2] << 8) | raw[3]

    # hi16 = voltage_mV, lo16 = current_mA (or current_mA * 100 for C3)
    # Typical: v = hi16 * 0.001 (V), c = lo16 * 0.001 (A), p = v * c (W)
    voltage = hi16 * 0.001
    current = lo16 * 0.001
    power = round(voltage * current, 3)

    return {"voltage": voltage, "current": current, "power": power}


class CuktechChargerCoordinator(DataUpdateCoordinator[ChargerState]):
    """Coordinator to manage BLE connection and data updates for CUKTECH charger."""

    def __init__(
        self,
        hass: HomeAssistant,
        mac: str,
        token: str,
        ble_key: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        token_bytes = bytes.fromhex(token)
        self._controller = CuktechBLEController(mac=mac, token=token_bytes)
        self._mac = mac
        self._ble_key = ble_key
        self._reconnect_task: asyncio.Task | None = None
        self._drain_task: asyncio.Task | None = None
        self._running = False
        self._port_push_callbacks: dict[int, list[Callable]] = {
            1: [], 2: [], 3: [], 4: []  # piid -> callbacks
        }
        self.data = ChargerState()

    @property
    def controller(self) -> CuktechBLEController:
        """Return the underlying BLE controller."""
        return self._controller

    async def _async_update_data(self) -> ChargerState:
        """Fetch data from the device (called periodically)."""
        if not self._controller.authenticated:
            await self._connect_and_auth()

        state = ChargerState()

        try:
            # Read all config properties
            props = await self._controller.get_properties([
                (SIID_CHARGER, PIID_SCENE_MODE),
                (SIID_CHARGER, PIID_SCREEN_TIMEOUT),
                (SIID_CHARGER, PIID_LANGUAGE),
                (SIID_CHARGER, PIID_PORT_CONTROL),
                (SIID_CHARGER, PIID_USB_A_ALWAYS_ON),
                (SIID_CHARGER, PIID_IDLE_SCREEN_OFF),
                (SIID_CHARGER, PIID_SCREEN_ORIENT_LOCK),
            ])

            state.scene_mode = props.get((SIID_CHARGER, PIID_SCENE_MODE))
            state.screen_timeout = props.get((SIID_CHARGER, PIID_SCREEN_TIMEOUT))
            state.language = props.get((SIID_CHARGER, PIID_LANGUAGE))
            state.port_control = props.get((SIID_CHARGER, PIID_PORT_CONTROL))
            state.usb_a_always_on = props.get((SIID_CHARGER, PIID_USB_A_ALWAYS_ON))
            state.idle_screen_off = props.get((SIID_CHARGER, PIID_IDLE_SCREEN_OFF))
            state.screen_orient_lock = props.get((SIID_CHARGER, PIID_SCREEN_ORIENT_LOCK))

            # Keep port data from push updates
            state.ports = self.data.ports
        except Exception as exc:
            _LOGGER.warning("Failed to fetch charger state: %s", exc)
            raise UpdateFailed(f"Failed to fetch data: {exc}") from exc

        return state

    async def _connect_and_auth(self) -> bool:
        """Connect and authenticate to the charger."""
        try:
            await self._controller.connect()
            _LOGGER.info("Connected to %s", self._mac)
            result = await self._controller.authenticate()
            if result:
                _LOGGER.info("Authenticated successfully to %s", self._mac)
                await self._start_background_drain()
                return True
            else:
                _LOGGER.error("Authentication failed for %s", self._mac)
                return False
        except Exception as exc:
            _LOGGER.exception("Failed to connect/auth to %s: %s", self._mac, exc)
            return False

    async def _start_background_drain(self) -> None:
        """Start background task that drains push notifications."""
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()

        self._drain_task = asyncio.create_task(self._background_drain())
        self._running = True

    async def _background_drain(self) -> None:
        """Background task: continuously drain push notifications from the device.

        This reuses the logic from _drain_device_push in a continuous loop.
        """
        port_piid_map = {1: "c1", 2: "c2", 3: "c3", 4: "a"}
        _LOGGER.debug("Background push drain started")

        while self._running and self._controller.client and self._controller.client.is_connected:
            try:
                data = await self._controller._wait_notify("cmd_recv", timeout=3.0)
                if not data or len(data) < 4:
                    continue

                if data[2] == 0x02 and len(data) >= 4:
                    encrypted_payload = data[4:]
                    await self._controller.client.write_gatt_char(
                        CHAR_CMD_RECV, bytes([0x00, 0x00, 0x03, 0x00]),
                        response=False,
                    )
                    pt = self._controller._decrypt(encrypted_payload)
                    if not pt or len(pt) < 8:
                        continue

                    b4 = pt[4]
                    piid = pt[7] if len(pt) > 7 else -1

                    # Handle port data push (piid 1-4, b4=0x04)
                    if b4 == 0x04 and piid in port_piid_map:
                        decoded = _decode_port_push(pt, piid)
                        if decoded:
                            port_name = port_piid_map[piid]
                            port_data = self.data.ports[port_name]
                            port_data.voltage = decoded["voltage"]
                            port_data.current = decoded["current"]
                            port_data.power = decoded["power"]
                            self.async_set_updated_data(self.data)

                    # Handle property change push (b4=0x04, piid > 4)
                    elif b4 == 0x04 and piid > 4:
                        val = pt[11] if len(pt) > 11 else None
                        if val is not None:
                            self._update_property(piid, val)

                elif data[2] == 0x00 and len(data) >= 6:
                    # Multi-frame push
                    frame_count = data[4] + 0x100 * data[5]
                    await self._controller.client.write_gatt_char(
                        CHAR_CMD_RECV, bytes([0x00, 0x00, 0x01, 0x01]),
                        response=False,
                    )
                    for _ in range(frame_count):
                        await self._controller._wait_notify("cmd_recv", timeout=3.0)
                    await self._controller.client.write_gatt_char(
                        CHAR_CMD_RECV, bytes([0x00, 0x00, 0x01, 0x00]),
                        response=False,
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.debug("Background drain error (non-critical): %s", exc)
                await asyncio.sleep(0.5)

        _LOGGER.debug("Background push drain ended")

    def _update_property(self, piid: int, value: int) -> None:
        """Update a known property in the stored state."""
        updates = {
            PIID_SCENE_MODE: "scene_mode",
            PIID_SCREEN_TIMEOUT: "screen_timeout",
            PIID_LANGUAGE: "language",
            PIID_PORT_CONTROL: "port_control",
            PIID_USB_A_ALWAYS_ON: "usb_a_always_on",
            PIID_IDLE_SCREEN_OFF: "idle_screen_off",
            PIID_SCREEN_ORIENT_LOCK: "screen_orient_lock",
        }
        attr = updates.get(piid)
        if attr:
            setattr(self.data, attr, value)
            self.async_set_updated_data(self.data)

    async def async_set_piid(self, piid: int, value: int) -> bool:
        """Set a PIID property on the charger.

        Returns True on success.
        """
        if not self._controller.authenticated:
            await self._connect_and_auth()

        try:
            result = await self._controller.send_miot_command(
                SIID_CHARGER, piid, value=value
            )
            if result:
                self._update_property(piid, value)
                return True
            return False
        except Exception as exc:
            _LOGGER.error("Failed to set PIID %d to %d: %s", piid, value, exc)
            return False

    async def async_get_port_control(self) -> int | None:
        """Read current port control bitmask (PIID 16)."""
        if not self._controller.authenticated:
            await self._connect_and_auth()

        try:
            result = await self._controller.send_miot_command(
                SIID_CHARGER, PIID_PORT_CONTROL
            )
            if result and result.get("value") is not None:
                self.data.port_control = result["value"]
                self.async_set_updated_data(self.data)
                return result["value"]
            return None
        except Exception as exc:
            _LOGGER.error("Failed to get port control: %s", exc)
            return None

    async def async_set_port_switch(
        self, port_key: str, turn_on: bool
    ) -> bool:
        """Set a specific port on/off by modifying PIID 16 bitmask."""
        bit = PORT_BITS.get(port_key)
        if bit is None:
            _LOGGER.error("Unknown port key: %s", port_key)
            return False

        # Read current value first
        current_val = self.data.port_control
        if current_val is None:
            current_val = await self.async_get_port_control()
        if current_val is None:
            current_val = 0

        if turn_on:
            new_val = current_val | (1 << bit)
        else:
            new_val = current_val & ~(1 << bit)

        return await self.async_set_piid(PIID_PORT_CONTROL, new_val)

    async def shutdown(self) -> None:
        """Shutdown the coordinator, disconnect and cancel tasks."""
        self._running = False
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
        await self._controller.disconnect()
