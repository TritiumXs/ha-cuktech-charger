#!/usr/bin/env python3
"""
Test driver for CUKTECH GaN Charger BLE integration.

Quickly test the BLE communication with your charger without Home Assistant.
Run this to verify your device works before setting up the HA integration.

Usage:
    # Scan for nearby CUKTECH chargers
    python test_driver.py scan

    # Quick test: scan, connect, auth, read status (requires token)
    python test_driver.py test --mac AA:BB:CC:DD:EE:FF --token YOUR_12BYTE_HEX_TOKEN

    # Full test with BLE key
    python test_driver.py test --mac AA:BB:CC:DD:EE:FF --token YOUR_TOKEN --ble-key YOUR_BLE_KEY

    # Or use environment variables
    export CUKTECH_DEVICE_MAC="AA:BB:CC:DD:EE:FF"
    export CUKTECH_DEVICE_TOKEN="your12bytehex"
    python test_driver.py test

Environment variables:
    CUKTECH_DEVICE_MAC      - Bluetooth MAC address
    CUKTECH_DEVICE_TOKEN    - 12-byte hex token (24 hex chars)
    CUKTECH_DEVICE_BLE_KEY  - 16-byte BLE key (32 hex chars, optional)
"""

import argparse
import asyncio
import os
import sys


def ensure_path():
    """Add the custom_components path so we can import _ble."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "custom_components", "cuktech_charger"))


async def cmd_scan(timeout: int = 10):
    """Scan for nearby CUKTECH chargers."""
    ensure_path()
    from _ble import UUID_FE95, BleakScanner

    print(f"🔍 Scanning for CUKTECH chargers ({timeout}s timeout)...")
    print(f"   Looking for service UUID: {UUID_FE95}")
    print()

    try:
        results = await BleakScanner.discover(timeout=timeout, return_adv=True)
    except Exception as exc:
        print(f"❌ BLE scan failed: {exc}")
        print("   Make sure Bluetooth is available and permissions are granted.")
        return None

    found = {}
    for mac, (device, adv) in results.items():
        uuids = adv.service_uuids if adv else []
        if UUID_FE95 in uuids:
            name = (adv.local_name if adv else None) or device.name or "Unknown"
            rssi = adv.rssi or 0
            found[mac] = {"name": name, "rssi": rssi}

    if not found:
        print("❌ No CUKTECH chargers found nearby.")
        print("   Make sure:")
        print("   1. Your charger is powered on")
        print("   2. Bluetooth is enabled on this computer")
        print("   3. The charger is within range (~10m)")
        print(f"\n   All {len(results)} devices seen:")
        for mac, (device, adv) in sorted(results.items(), key=lambda x: x[1][1].rssi or -999, reverse=True):
            name = (adv.local_name if adv else None) or device.name or "Unknown"
            rssi = adv.rssi or 0
            uuids = ",".join(adv.service_uuids) if adv and adv.service_uuids else "none"
            print(f"     {mac}  RSSI={rssi:4d}  {name}  uuids={uuids}")
        return None

    print(f"✅ Found {len(found)} CUKTECH charger(s):")
    print()
    for mac, info in sorted(found.items(), key=lambda x: x[1]["rssi"], reverse=True):
        print(f"   📱 {info['name']}")
        print(f"      MAC:  {mac}")
        print(f"      RSSI: {info['rssi']} dBm")
        print()

    return found


async def cmd_test(mac: str, token: str, ble_key: str | None = None):
    """Run a full connectivity test."""
    ensure_path()
    from _ble import CuktechBLEController, PIID_NAMES, PIID_DISPLAY, SIID_CHARGER

    print("🧪 CUKTECH Charger Test Suite")
    print(f"   MAC:   {mac}")
    print(f"   Token: {token[:4]}...{token[-4:]}")
    if ble_key:
        print(f"   BLE Key: {ble_key[:4]}...{ble_key[-4:]}")
    print()

    # Validate inputs
    try:
        token_bytes = bytes.fromhex(token)
    except ValueError:
        print("❌ Token is not valid hex!")
        return False
    if len(token_bytes) != 12:
        print(f"❌ Token must be 12 bytes (24 hex chars), got {len(token_bytes)} bytes")
        return False

    key_bytes = None
    if ble_key:
        try:
            key_bytes = bytes.fromhex(ble_key)
        except ValueError:
            print("❌ BLE key is not valid hex!")
            return False
        if len(key_bytes) != 16:
            print(f"❌ BLE key must be 16 bytes (32 hex chars), got {len(key_bytes)} bytes")
            return False

    all_passed = True
    ctrl = CuktechBLEController(mac=mac, token=token_bytes)

    try:
        # ── Test 1: Connect ──
        print("─" * 50)
        print("📡 Test 1/4: Connect to device...")
        try:
            connected = await ctrl.connect()
            if connected:
                print("   ✅ Connected successfully")
            else:
                print("   ❌ Connection failed")
                all_passed = False
        except Exception as exc:
            print(f"   ❌ Connection error: {exc}")
            all_passed = False

        if not all_passed:
            return False

        # ── Test 2: Device Info ──
        print("─" * 50)
        print("📋 Test 2/4: Read device info...")
        try:
            await ctrl.read_device_info()
            print("   ✅ Device info read successfully")
        except Exception as exc:
            print(f"   ⚠️  Device info error (non-fatal): {exc}")

        # ── Test 3: Authenticate ──
        print("─" * 50)
        print("🔐 Test 3/4: Authenticate...")
        try:
            auth_ok = await ctrl.authenticate()
            if auth_ok:
                print("   ✅ Authentication successful")
            else:
                print("   ❌ Authentication failed")
                print("   Common causes:")
                print("   1. Incorrect token (must be from YOUR device)")
                print("   2. Device bound to a different Mi Home account")
                print("   3. Token expired (unbind and rebind in Mi Home)")
                all_passed = False
        except Exception as exc:
            print(f"   ❌ Authentication error: {exc}")
            all_passed = False

        if not all_passed:
            return False

        # ── Test 4: Read Status ──
        print("─" * 50)
        print("📊 Test 4/4: Read charger status...")
        status_ok = True
        props_to_read = list(range(1, 21))
        # Skip write-only PIID 14
        props_to_read.remove(14)

        for piid in props_to_read:
            try:
                result = await ctrl.send_miot_command(SIID_CHARGER, piid)
                if result and result.get("value") is not None:
                    val = result["value"]
                    name = PIID_NAMES.get(piid, f"PIID-{piid}")
                    display = PIID_DISPLAY.get(piid, {})
                    display_str = f" → {display[val]}" if val in display else ""
                    print(f"   ✅ PIID {piid:2d} [{name:12s}] = {val}{display_str}")
                else:
                    name = PIID_NAMES.get(piid, f"PIID-{piid}")
                    print(f"   ⚠️  PIID {piid:2d} [{name:12s}] = no response")
                    status_ok = False
            except Exception as exc:
                name = PIID_NAMES.get(piid, f"PIID-{piid}")
                print(f"   ❌ PIID {piid:2d} [{name:12s}] = error: {exc}")
                status_ok = False

        if status_ok:
            print("   ✅ All properties read successfully")
        else:
            print("   ⚠️  Some properties failed to read (may be normal for unsupported PIIDs)")

    finally:
        print("─" * 50)
        print("🔌 Disconnecting...")
        await ctrl.disconnect()
        print("   Done.")

    print()
    if all_passed:
        print("🎉 All tests passed! Your charger is ready for Home Assistant integration.")
    else:
        print("❌ Some tests failed. Review the output above for details.")
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="CUKTECH GaN Charger - Test Driver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_driver.py scan
  python test_driver.py test --mac AA:BB:CC:DD:EE:FF --token abc123...def456
  python test_driver.py test --mac AA:BB:CC:DD:EE:FF --token abc... --ble-key def...
        """,
    )

    sub = parser.add_subparsers(dest="command", help="Test command")

    # scan
    scan_p = sub.add_parser("scan", help="Scan for nearby CUKTECH chargers")
    scan_p.add_argument("--timeout", type=int, default=10, help="Scan timeout in seconds")

    # test
    test_p = sub.add_parser("test", help="Run full connectivity test")
    test_p.add_argument(
        "--mac",
        default=os.environ.get("CUKTECH_DEVICE_MAC", ""),
        help="Device MAC address (or set CUKTECH_DEVICE_MAC env var)",
    )
    test_p.add_argument(
        "--token",
        default=os.environ.get("CUKTECH_DEVICE_TOKEN", ""),
        help="12-byte hex token (or set CUKTECH_DEVICE_TOKEN env var)",
    )
    test_p.add_argument(
        "--ble-key",
        default=os.environ.get("CUKTECH_DEVICE_BLE_KEY", ""),
        help="16-byte BLE key (or set CUKTECH_DEVICE_BLE_KEY env var)",
    )

    args = parser.parse_args()

    if args.command == "scan":
        asyncio.run(cmd_scan(args.timeout))
    elif args.command == "test":
        if not args.mac:
            print("❌ MAC address required. Use --mac or set CUKTECH_DEVICE_MAC env var.")
            print("   Run 'python test_driver.py scan' to find your device first.")
            sys.exit(1)
        if not args.token:
            print("❌ Token required. Use --token or set CUKTECH_DEVICE_TOKEN env var.")
            sys.exit(1)
        ble_key = args.ble_key if args.ble_key else None
        success = asyncio.run(cmd_test(args.mac, args.token, ble_key))
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
