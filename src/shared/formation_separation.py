"""When one voice parse yields several vehicles to the same waypoint, spread targets.

Without this, "Alpha and Bravo, fly to the tower" becomes two MOVEs with identical
lat/lon/alt and the sim aircraft stack on the same point (collisions).

We only adjust commands that share a grouped location in the *same batch* (same NLU
response). Single-vehicle moves stay on the exact coordinates.
"""

from __future__ import annotations

import copy
import logging
import math
import os
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ~1.1 m latitude resolution — treat as "same named waypoint"
_LOC_ROUND = 5

# Lateral spacing along east–west axis (meters). Tune with env if needed.
_DEFAULT_SPACING_M = float(os.environ.get("FORMATION_SPACING_M", "22"))
_DEFAULT_ALT_STAGGER_M = float(os.environ.get("FORMATION_ALT_STAGGER_M", "7"))


def _command_types_with_top_level_location() -> frozenset[str]:
    return frozenset({"move", "loiter", "overwatch", "engage", "patrol"})


def _location_group_key(cmd: dict[str, Any]) -> tuple[float, float, float] | None:
    loc = cmd.get("location")
    if not isinstance(loc, dict):
        return None
    try:
        lat = float(loc["lat"])
        lon = float(loc["lon"])
        alt = float(loc.get("alt_m", 0.0))
    except (KeyError, TypeError, ValueError):
        return None
    return (round(lat, _LOC_ROUND), round(lon, _LOC_ROUND), round(alt, 1))


def apply_formation_separation(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a deep copy of ``commands`` with duplicate waypoint targets separated.

    If ``FORMATION_SEPARATION=0`` in the environment, returns a deep copy unchanged
    (aside from copy overhead) — effectively disabled.
    """
    out = copy.deepcopy(commands)
    if os.environ.get("FORMATION_SEPARATION", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return out

    spacing_m = max(5.0, _DEFAULT_SPACING_M)
    alt_stagger = max(0.0, _DEFAULT_ALT_STAGGER_M)
    types_ok = _command_types_with_top_level_location()

    by_key: dict[tuple[float, float, float], list[int]] = defaultdict(list)
    for i, cmd in enumerate(out):
        ct = (cmd.get("command_type") or "").lower()
        if ct not in types_ok:
            continue
        key = _location_group_key(cmd)
        if key is None:
            continue
        by_key[key].append(i)

    for key, indices in by_key.items():
        if len(indices) < 2:
            continue
        callsigns = [str(out[i].get("vehicle_callsign", "")).upper() for i in indices]
        if len(set(callsigns)) < len(callsigns):
            # Duplicate rows for the same vehicle — do not rewrite
            continue
        if len(set(callsigns)) < 2:
            continue

        # Deterministic order: Alpha before Bravo, etc.
        indices.sort(key=lambda i: str(out[i].get("vehicle_callsign", "")).upper())

        lat0 = float(out[indices[0]]["location"]["lat"])
        n = len(indices)
        meters_per_deg_lon = 111_320.0 * max(0.2, math.cos(math.radians(lat0)))

        for slot, idx in enumerate(indices):
            loc = out[idx]["location"]
            offset_m = (slot - (n - 1) / 2.0) * spacing_m
            dlon = offset_m / meters_per_deg_lon
            loc["lon"] = float(loc["lon"]) + dlon
            base_alt = float(loc.get("alt_m", 12.0))
            loc["alt_m"] = base_alt + slot * alt_stagger
            logger.info(
                "Formation separation: %s slot %d/%d → lon %+f, alt_m %.1f (same waypoint batch)",
                out[idx].get("vehicle_callsign"),
                slot + 1,
                n,
                dlon,
                loc["alt_m"],
            )

    return out
