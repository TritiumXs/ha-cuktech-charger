"""Constants for the CUKTECH GaN Charger integration."""

DOMAIN = "cuktech_charger"

# MiOT Service
SIID_CHARGER = 2

# PIID definitions (SIID=2)
PIID_PORT_C1 = 1
PIID_PORT_C2 = 2
PIID_PORT_C3 = 3
PIID_PORT_A = 4
PIID_SCENE_MODE = 5
PIID_SCREEN_TIMEOUT = 6
PIID_LANGUAGE = 13
PIID_USB_A_ALWAYS_ON = 15
PIID_PORT_CONTROL = 16
PIID_IDLE_SCREEN_OFF = 19
PIID_SCREEN_ORIENT_LOCK = 20

# Port bit positions within PIID 16
PORT_BITS = {"c1": 0, "c2": 1, "c3": 2, "a": 3}

# PIID display names
PIID_NAMES = {
    1: "C1 Port",
    2: "C2 Port",
    3: "C3 Port",
    4: "A Port",
    5: "Scene Mode",
    6: "Screen Timeout",
    7: "Protocol Control",
    8: "Timer Setting",
    9: "C1 Timer",
    10: "C2 Timer",
    11: "C3 Timer",
    12: "A Timer",
    13: "Language",
    14: "Enter Interface",
    15: "USB-A Always On",
    16: "Port Control",
    17: "Unknown-17",
    18: "Unknown-18",
    19: "Idle Screen Off",
    20: "Screen Orient Lock",
}

# Display value mappings
PIID_DISPLAY = {
    5: {1: "AI Mode", 2: "Digital Ecosystem", 3: "Single Port", 4: "Balanced"},
    6: {0: "5 min", 1: "1 min (old)", 2: "10 min", 3: "30 min", 4: "Always On", 5: "1 min"},
    13: {0: "English", 1: "中文"},
    15: {0: "Off", 1: "On"},
    19: {0: "Off", 1: "On"},
    20: {0: "Off", 1: "On"},
}

# Select entity options
OPTIONS_SCENE_MODE = ["AI Mode", "Digital Ecosystem", "Single Port", "Balanced"]
OPTIONS_SCREEN_TIMEOUT = ["5 min", "1 min", "10 min", "30 min", "Always On"]
OPTIONS_LANGUAGE = ["English", "中文"]

# Value mappings for select entities
SCENE_MODE_VALUE_MAP = {0: "AI Mode", 1: "Digital Ecosystem", 2: "Single Port", 3: "Balanced"}
SCENE_MODE_REVERSE_MAP = {"AI Mode": 0, "Digital Ecosystem": 1, "Single Port": 2, "Balanced": 3}

SCREEN_TIMEOUT_VALUE_MAP = {0: "5 min", 1: "1 min", 2: "10 min", 3: "30 min", 4: "Always On"}
SCREEN_TIMEOUT_REVERSE_MAP = {"5 min": 0, "1 min": 1, "10 min": 2, "30 min": 3, "Always On": 4}
# Note: value 5 "1 min" is mapped to option "1 min" (same as value 1)
SCREEN_TIMEOUT_VALUE_MAP[5] = "1 min"

LANGUAGE_VALUE_MAP = {0: "English", 1: "中文"}
LANGUAGE_REVERSE_MAP = {"English": 0, "中文": 1}

# Port names
PORT_NAMES = {"c1": "C1", "c2": "C2", "c3": "C3", "a": "A"}

# Sensor attributes
VOLTAGE = "voltage"
CURRENT = "current"
POWER = "power"

# Default update interval (seconds)
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_RECONNECT_DELAY = 10

# Error states
ERROR_NOT_CONNECTED = "not_connected"
ERROR_NO_DATA = "no_data"
