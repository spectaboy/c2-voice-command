"""Configurable battlespace loader.

On hackathon day, waypoints/entities/fleet files are provided via env vars.
Falls back to compound waypoints (Fort Huachuca-style compound, origin 32.990, -106.975).

Env vars:
  BATTLESPACE_WAYPOINTS — path to JSON file with waypoint definitions
  BATTLESPACE_ENTITIES  — path to JSON file with IFF entity preloads
  BATTLESPACE_FLEET     — path to JSON file with fleet vehicle config
"""

import json
import logging
import os
from typing import Any

from src.shared.constants import VEHICLES

logger = logging.getLogger(__name__)

# Default compound waypoints — origin 32.990, -106.975, 1400m ASL
# ENU coordinates (x=East, y=North) converted to GPS
DEFAULT_WAYPOINTS = {
    "landing pad": {"lat": 32.99, "lon": -106.9754291},
    "the landing pad": {"lat": 32.99, "lon": -106.9754291},
    "launch pad": {"lat": 32.99, "lon": -106.9754291},
    "the launch pad": {"lat": 32.99, "lon": -106.9754291},
    "the pad": {"lat": 32.99, "lon": -106.9754291},
    "home": {"lat": 32.99, "lon": -106.9754291},
    "base": {"lat": 32.99, "lon": -106.9754291},

    "gate": {"lat": 32.99, "lon": -106.9756437},
    "the gate": {"lat": 32.99, "lon": -106.9756437},
    "west gate": {"lat": 32.99, "lon": -106.9756437},
    "the west gate": {"lat": 32.99, "lon": -106.9756437},

    "northwest tower": {"lat": 32.9903329, "lon": -106.9756115},
    "northwest watch tower": {"lat": 32.9903329, "lon": -106.9756115},
    "NW tower": {"lat": 32.9903329, "lon": -106.9756115},
    "the northwest tower": {"lat": 32.9903329, "lon": -106.9756115},
    "the northwest watch tower": {"lat": 32.9903329, "lon": -106.9756115},

    "northeast tower": {"lat": 32.9903329, "lon": -106.9743885},
    "northeast watch tower": {"lat": 32.9903329, "lon": -106.9743885},
    "NE tower": {"lat": 32.9903329, "lon": -106.9743885},
    "the northeast tower": {"lat": 32.9903329, "lon": -106.9743885},
    "the northeast watch tower": {"lat": 32.9903329, "lon": -106.9743885},

    "southeast tower": {"lat": 32.9896671, "lon": -106.9743885},
    "southeast watch tower": {"lat": 32.9896671, "lon": -106.9743885},
    "SE tower": {"lat": 32.9896671, "lon": -106.9743885},
    "the southeast tower": {"lat": 32.9896671, "lon": -106.9743885},
    "the southeast watch tower": {"lat": 32.9896671, "lon": -106.9743885},

    "southwest tower": {"lat": 32.9896671, "lon": -106.9756115},
    "southwest watch tower": {"lat": 32.9896671, "lon": -106.9756115},
    "SW tower": {"lat": 32.9896671, "lon": -106.9756115},
    "the southwest tower": {"lat": 32.9896671, "lon": -106.9756115},
    "the southwest watch tower": {"lat": 32.9896671, "lon": -106.9756115},

    "command building": {"lat": 32.990126, "lon": -106.9747318},
    "the command building": {"lat": 32.990126, "lon": -106.9747318},
    "command": {"lat": 32.990126, "lon": -106.9747318},
    "rooftop": {"lat": 32.990126, "lon": -106.9747318},
    "the rooftop": {"lat": 32.990126, "lon": -106.9747318},
    "rooftop structure": {"lat": 32.990126, "lon": -106.9747318},
    "cmd building": {"lat": 32.990126, "lon": -106.9747318},

    "containers": {"lat": 32.9898515, "lon": -106.9749839},
    "the containers": {"lat": 32.9898515, "lon": -106.9749839},
    "shipping containers": {"lat": 32.9898515, "lon": -106.9749839},
    "the shipping containers": {"lat": 32.9898515, "lon": -106.9749839},

    "motor pool": {"lat": 32.98982, "lon": -106.9745923},
    "the motor pool": {"lat": 32.98982, "lon": -106.9745923},
    "motorpool": {"lat": 32.98982, "lon": -106.9745923},

    "fuel depot": {"lat": 32.9897121, "lon": -106.9752897},
    "the fuel depot": {"lat": 32.9897121, "lon": -106.9752897},

    "comms tower": {"lat": 32.9902699, "lon": -106.9745709},
    "the comms tower": {"lat": 32.9902699, "lon": -106.9745709},
    "communications tower": {"lat": 32.9902699, "lon": -106.9745709},

    "barracks north": {"lat": 32.990225, "lon": -106.9752146},
    "north barracks": {"lat": 32.990225, "lon": -106.9752146},
    "barracks 1": {"lat": 32.990225, "lon": -106.9752146},
    "barracks south": {"lat": 32.989775, "lon": -106.9752146},
    "south barracks": {"lat": 32.989775, "lon": -106.9752146},
    "barracks 2": {"lat": 32.989775, "lon": -106.9752146},
    "barracks": {"lat": 32.990225, "lon": -106.9752146},

    # NATO phonetic aliases (Alpha-Hotel) → primary compound waypoints
    "Alpha": {"lat": 32.99, "lon": -106.9754291},
    "waypoint alpha": {"lat": 32.99, "lon": -106.9754291},
    "Bravo": {"lat": 32.99, "lon": -106.9756437},
    "waypoint bravo": {"lat": 32.99, "lon": -106.9756437},
    "Charlie": {"lat": 32.9903329, "lon": -106.9756115},
    "waypoint charlie": {"lat": 32.9903329, "lon": -106.9756115},
    "Delta": {"lat": 32.9903329, "lon": -106.9743885},
    "waypoint delta": {"lat": 32.9903329, "lon": -106.9743885},
    "Echo": {"lat": 32.9896671, "lon": -106.9743885},
    "waypoint echo": {"lat": 32.9896671, "lon": -106.9743885},
    "Foxtrot": {"lat": 32.9896671, "lon": -106.9756115},
    "waypoint foxtrot": {"lat": 32.9896671, "lon": -106.9756115},
    "Golf": {"lat": 32.990126, "lon": -106.9747318},
    "waypoint golf": {"lat": 32.990126, "lon": -106.9747318},
    "Hotel": {"lat": 32.98982, "lon": -106.9745923},
    "waypoint hotel": {"lat": 32.98982, "lon": -106.9745923},
}


_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

# Default file paths (relative to project root)
_DEFAULT_FILES = {
    "BATTLESPACE_WAYPOINTS": os.path.join(_DATA_DIR, "waypoints.json"),
    "BATTLESPACE_ENTITIES": os.path.join(_DATA_DIR, "entities.json"),
    "BATTLESPACE_FLEET": os.path.join(_DATA_DIR, "fleet.json"),
}


def _load_json(env_var: str) -> dict | list | None:
    """Load JSON from env var path, or fall back to default data/ file."""
    path = os.environ.get(env_var, "")
    if not path:
        path = _DEFAULT_FILES.get(env_var, "")
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        logger.info("Loaded %s from %s", env_var, path)
        return data
    except Exception as e:
        logger.warning("Failed to load %s from %s: %s", env_var, path, e)
        return None


def load_waypoints() -> dict[str, dict[str, float]]:
    """Load waypoints from BATTLESPACE_WAYPOINTS or fall back to defaults.

    Expected JSON format: {"WaypointName": {"lat": float, "lon": float}, ...}
    """
    data = _load_json("BATTLESPACE_WAYPOINTS")
    if data and isinstance(data, dict):
        return data
    return DEFAULT_WAYPOINTS


def load_entities() -> list[dict[str, Any]]:
    """Load pre-defined entities from BATTLESPACE_ENTITIES.

    Expected JSON format: [{"uid": str, "affiliation": "f"|"h"|"u"|"n",
                            "lat": float, "lon": float, "alt": float,
                            "heading": float, "speed": float, "domain": str}, ...]
    Returns empty list if not configured.
    """
    data = _load_json("BATTLESPACE_ENTITIES")
    if data and isinstance(data, list):
        return data
    return []


def load_fleet() -> dict[str, dict[str, Any]]:
    """Load fleet config from BATTLESPACE_FLEET or fall back to constants.VEHICLES.

    Expected JSON format: same as VEHICLES dict in constants.py
    """
    data = _load_json("BATTLESPACE_FLEET")
    if data and isinstance(data, dict):
        return data
    return VEHICLES


def get_active_vehicles() -> dict[str, dict[str, Any]]:
    """Get the active vehicle configuration (fleet file or defaults)."""
    return load_fleet()


def build_waypoint_prompt_section() -> str:
    """Build the waypoint section for the NLU system prompt."""
    waypoints = load_waypoints()
    lines = []
    for name, coords in waypoints.items():
        lat = coords.get("lat", 0.0)
        lon = coords.get("lon", 0.0)
        lines.append(f"- {name}: {lat}, {lon}")
    return "\n".join(lines)


def build_entity_prompt_section() -> str:
    """Build the entity/contacts section for the NLU system prompt."""
    entities = load_entities()
    if not entities:
        return "No known contacts."
    affil_labels = {"f": "FRIENDLY", "h": "HOSTILE", "u": "UNKNOWN", "n": "NEUTRAL"}
    lines = []
    for e in entities:
        uid = e.get("uid", "?")
        name = e.get("name", uid)
        affil = affil_labels.get(e.get("affiliation", "u"), "UNKNOWN")
        domain = e.get("domain", "ground")
        lat = e.get("lat", 0.0)
        lon = e.get("lon", 0.0)
        lines.append(f"- {name} (uid={uid}): {affil}, {domain}, at {lat}, {lon}")
    return "\n".join(lines)
