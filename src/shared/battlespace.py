"""Configurable battlespace loader.

On hackathon day, waypoints/entities/fleet files are provided via env vars.
Falls back to hardcoded defaults (Halifax landmarks, default VEHICLES dict).

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

# Default Halifax waypoints (used when no file is provided)
DEFAULT_WAYPOINTS = {
    # Major landmarks
    "Halifax Harbor": {"lat": 44.6425, "lon": -63.5670},
    "the harbor": {"lat": 44.6425, "lon": -63.5670},
    "Citadel Hill": {"lat": 44.6478, "lon": -63.5802},
    "the citadel": {"lat": 44.6478, "lon": -63.5802},
    "HMC Dockyard": {"lat": 44.6620, "lon": -63.5880},
    "the dockyard": {"lat": 44.6620, "lon": -63.5880},
    "Point Pleasant Park": {"lat": 44.6230, "lon": -63.5690},
    "the park": {"lat": 44.6230, "lon": -63.5690},
    "Georges Island": {"lat": 44.6380, "lon": -63.5620},
    "McNabs Island": {"lat": 44.6190, "lon": -63.5340},
    "Halifax Waterfront": {"lat": 44.6460, "lon": -63.5680},
    "the waterfront": {"lat": 44.6460, "lon": -63.5680},
    "Pier 21": {"lat": 44.6390, "lon": -63.5660},
    "Bedford Basin": {"lat": 44.6800, "lon": -63.6300},
    "the basin": {"lat": 44.6800, "lon": -63.6300},
    "Angus L. Macdonald Bridge": {"lat": 44.6630, "lon": -63.5630},
    "the bridge": {"lat": 44.6630, "lon": -63.5630},
    "Dartmouth": {"lat": 44.6650, "lon": -63.5590},
    "CFB Halifax": {"lat": 44.6510, "lon": -63.5820},
    "Halifax Commons": {"lat": 44.6510, "lon": -63.5840},
    "the commons": {"lat": 44.6510, "lon": -63.5840},
    "Nathan Green Square": {"lat": 44.6482, "lon": -63.5710},
    "Chebucto Landing": {"lat": 44.6492, "lon": -63.5668},

    # Major streets (midpoints for navigation)
    "Barrington Street": {"lat": 44.6480, "lon": -63.5728},
    "Duke Street": {"lat": 44.6490, "lon": -63.5740},
    "Prince Street": {"lat": 44.6472, "lon": -63.5735},
    "Argyle Street": {"lat": 44.6468, "lon": -63.5755},
    "Hollis Street": {"lat": 44.6480, "lon": -63.5710},
    "Granville Street": {"lat": 44.6478, "lon": -63.5720},
    "Upper Water Street": {"lat": 44.6490, "lon": -63.5690},
    "Lower Water Street": {"lat": 44.6465, "lon": -63.5685},
    "Brunswick Street": {"lat": 44.6500, "lon": -63.5760},
    "Gottingen Street": {"lat": 44.6520, "lon": -63.5770},
    "Cogswell Street": {"lat": 44.6515, "lon": -63.5745},
    "Sackville Street": {"lat": 44.6460, "lon": -63.5740},
    "Spring Garden Road": {"lat": 44.6430, "lon": -63.5780},
    "South Park Street": {"lat": 44.6420, "lon": -63.5770},
    "Rainnie Drive": {"lat": 44.6505, "lon": -63.5785},

    # Key intersections
    "Barrington and Duke": {"lat": 44.6490, "lon": -63.5727},
    "Barrington and Prince": {"lat": 44.6473, "lon": -63.5726},
    "Barrington and Sackville": {"lat": 44.6458, "lon": -63.5724},
    "Barrington and Spring Garden": {"lat": 44.6435, "lon": -63.5722},
    "Duke and Hollis": {"lat": 44.6492, "lon": -63.5712},
    "Duke and Granville": {"lat": 44.6491, "lon": -63.5720},
    "Duke and Argyle": {"lat": 44.6489, "lon": -63.5745},
    "Duke and Brunswick": {"lat": 44.6490, "lon": -63.5758},
    "Prince and Hollis": {"lat": 44.6474, "lon": -63.5710},
    "Prince and Granville": {"lat": 44.6473, "lon": -63.5718},
    "Argyle and Prince": {"lat": 44.6471, "lon": -63.5745},
    "Gottingen and Cogswell": {"lat": 44.6525, "lon": -63.5768},
    "Gottingen and Duke": {"lat": 44.6500, "lon": -63.5772},

    # Regions
    "North End": {"lat": 44.6600, "lon": -63.5800},
    "South End": {"lat": 44.6300, "lon": -63.5750},
    "Downtown": {"lat": 44.6480, "lon": -63.5730},
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
