# Service ports
VOICE_PORT = 8001
NLU_PORT = 8002
COORDINATOR_PORT = 8000
MAVLINK_BRIDGE_PORT = 8003
IFF_PORT = 8004
WS_PORT = 8005
DASHBOARD_PORT = 3000
FTS_COT_PORT = 8087
FTS_REST_PORT = 19023
FTS_WEBUI_PORT = 5000

# SITL vehicles — port = 5760 + (instance * 10)
VEHICLES = {
    "UAV-1": {"sitl_port": 5760, "sysid": 1, "type": "ArduCopter", "cot_type": "a-f-A-M-F-Q-r", "domain": "air"},
    "UAV-2": {"sitl_port": 5770, "sysid": 2, "type": "ArduCopter", "cot_type": "a-f-A-M-F-Q-r", "domain": "air"},
    "UAV-3": {"sitl_port": 5780, "sysid": 3, "type": "ArduCopter", "cot_type": "a-f-A-M-F-Q-r", "domain": "air"},
    "UGV-1": {"sitl_port": 5790, "sysid": 4, "type": "Rover",      "cot_type": "a-f-G-E-V",     "domain": "ground"},
    "UGV-2": {"sitl_port": 5800, "sysid": 5, "type": "Rover",      "cot_type": "a-f-G-E-V",     "domain": "ground"},
    "USV-1": {"sitl_port": 5810, "sysid": 6, "type": "Rover",      "cot_type": "a-f-S-X",       "domain": "maritime", "frame": "motorboat"},
}

# Callsign aliases for NLU resolution
# Updated dynamically from fleet config, but keep common defaults
CALLSIGN_ALIASES = {
    "alpha": "Alpha",
    "bravo": "Bravo",
    "drone 1": "Alpha",
    "drone 2": "Bravo",
    "the first drone": "Alpha",
    "the second drone": "Bravo",
    "the drone": "Alpha",
    "uav 1": "Alpha",
    "uav 2": "Bravo",
    "uav-1": "Alpha",
    "uav-2": "Bravo",
}

def get_active_vehicles():
    """Get active vehicle config — delegates to battlespace loader if available."""
    from src.shared.battlespace import load_fleet
    return load_fleet()


# CoT type strings (MIL-STD-2525)
COT_TYPES = {
    ("air", "f"):      "a-f-A-M-F-Q-r",
    ("air", "h"):      "a-h-A-M-F-Q-r",
    ("air", "u"):      "a-u-A",
    ("ground", "f"):   "a-f-G-E-V",
    ("ground", "h"):   "a-h-G-E-V",
    ("ground", "u"):   "a-u-G",
    ("maritime", "f"): "a-f-S-X",
    ("maritime", "h"): "a-h-S-X",
    ("maritime", "u"): "a-u-S",
}
