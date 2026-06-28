# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Home Assistant custom integration for CUKTECH GaN Charger Ultra (Xiaomi ecosystem). Communicates with the charger over BLE using the MiOT protocol — no cloud required. The upstream CLI tool lives at `github.com:zhyzhaogit/cuktech-ble-controller`.

## Commands

```bash
# Standalone BLE scan (no HA needed)
python test_driver.py scan

# Full device test (connect + auth + read all properties)
python test_driver.py test --mac AA:BB:CC:DD:EE:FF --token 4160c5d6a560e6fcd81cfcf6

# Syntax check all Python files
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ...]"
```

There is no test suite, linter, or build step. `_ble.py` can also run standalone: `python -m custom_components.cuktech_charger._ble scan|info|auth|status|...`.

## Architecture

```
_ble.py                         ← BLE/MiOT protocol layer (standalone, no HA imports)
  CuktechBLEController          ← connect, authenticate (HKDF challenge-response),
                                  encrypt/decrypt (AES-CCM), send MiOT GET/SET commands

coordinator.py                  ← HA DataUpdateCoordinator wrapping the BLE controller
  CuktechChargerCoordinator     ← periodic poll + background push drain + port-switch helper

__init__.py                     ← HA entry point: async_setup_entry / async_unload_entry
config_flow.py                  ← Config flow with 4 steps + auto-discovery
sensor.py / switch.py / select.py  ← HA platform entities
const.py                        ← PIID constants, value maps, port definitions
test_driver.py                  ← Standalone test harness (independent of HA)
```

### Config flow steps

```
async_step_user         → scan (HA Bluetooth cache + BleakScanner fallback) → pick device list
async_step_bluetooth    → HA-triggered auto-discovery (MAC pre-filled) → goes straight to token
async_step_manual       → manual MAC entry (fallback when scan finds nothing)
async_step_token        → enter token + optional BLE key → validate → create_entry
```

### Device identification — CRITICAL

**Devices are identified by BLE local-name containing `"njcuk"` (case-insensitive), NOT by UUID 0xFE95.** The upstream project uses `"njcuk" in name.lower()`. CUKTECH chargers broadcast names like `njcuk.fitting.ad1204`. UUID-based matching fails on ESPHome Bluetooth Proxies because they place the UUID in `service_data` keys rather than in `service_uuids`.

### BLE protocol layers (inside `_ble.py`)

1. **GATT** — Service 0xFE95 with characteristics for device-info, auth-control, auth-data, cmd-send, cmd-recv, fw-version. All notification channels are pre-subscribed in `connect()`.
2. **MiOT auth** — HKDF-SHA256 key derivation from token + random nonce exchange, HMAC verification.
3. **MiOT command framing** — GET/SET messages encrypted with AES-CCM, sent over cmd-send, responses arrive on cmd-recv.
4. **Push notifications** — Port data (PIID 1-4) arrives as unsolicited encrypted pushes; must be ACKed promptly or the device stops sending.

### PIID reference (SIID=2 charger service)

| PIID | Name | Type |
|------|------|------|
| 1-4 | C1/C2/C3/A port data | Push (notify) |
| 5 | Scene mode | R/W (1=AI, 2=Apple, 3=Single, 4=Balanced) |
| 6 | Screen timeout | R/W |
| 13 | Language | R/W (0=EN, 1=CN) |
| 15 | USB-A always on | R/W |
| 16 | Port control bitmap | R/W (bit0=C1, bit1=C2, bit2=C3, bit3=A) |
| 19 | Idle screen off | R/W |
| 20 | Screen orientation lock | R/W |

### Home Assistant specifics

- Config entry data uses `CONF_ADDRESS` (not `CONF_MAC`), stored under key `"address"`.
- Token and ble_key are stored under `"token"` and `"ble_key"` keys (plain strings, not HA constants).
- `CuktechBLEController.__init__` takes `mac: str`, `token: bytes` (12 bytes), `product_id: int = 0x660e`.
- The `coordinator._connect_and_auth()` passes `token_bytes = bytes.fromhex(token)`.

## Git workflow notes

- The upstream refactored config flow (`98f7a67`) to scan-first-then-auth architecture, removing manual MAC entry. Manual MAC entry was restored because BLE scanning does not always find the charger (adapter conflicts, proxy data paths).
- Importing the string literal `"token"` in `from homeassistant.const import ...` is a Python syntax error — `"token"` is a dict key, not a constant.
- `async_discovered_service_info` is a **sync** function despite the `async_` prefix (HA convention). Call it without `await`.
