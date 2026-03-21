"""Core NLU: call Claude with tool-calling to parse transcripts into MilitaryCommands."""

import json
import math
import os
import logging
import re
from pathlib import Path
from typing import Union

import anthropic
import httpx

from src.shared.schemas import (
    CommandType,
    Domain,
    Location,
    MilitaryCommand,
    RiskLevel,
)
from src.shared.constants import VEHICLES, CALLSIGN_ALIASES, MAVLINK_BRIDGE_PORT
from src.shared.battlespace import build_waypoint_prompt_section, build_entity_prompt_section, get_active_vehicles
from .tools import TOOLS, TOOL_TO_COMMAND_TYPE
from .context import NLUContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entity alias map — maps various operator names to canonical IFF UIDs
# ---------------------------------------------------------------------------

_entity_alias_map: dict[str, str] = {}  # lower-case alias → canonical uid


def _load_entity_aliases() -> None:
    """Build a case-insensitive alias map from the entity list JSON.

    Populates ``_entity_alias_map`` from:
      - uid
      - callsign (if different from uid)
      - common variations (dashes removed, spaces collapsed, etc.)
    """
    global _entity_alias_map
    entity_path = os.getenv(
        "ENTITY_LIST_PATH",
        str(Path(__file__).resolve().parent.parent.parent / "data" / "entity_list.json"),
    )
    if not os.path.isfile(entity_path):
        logger.info("No entity list at %s — skipping alias map", entity_path)
        return

    try:
        raw = json.loads(Path(entity_path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load entity list for NLU aliases: %s", exc)
        return

    entities = raw.get("entities", raw) if isinstance(raw, dict) else raw
    alias_map: dict[str, str] = {}
    for ent in entities:
        uid = ent.get("uid", "")
        if not uid:
            continue
        callsign = ent.get("callsign", uid)

        # Add all variations
        for value in {uid, callsign}:
            low = value.lower()
            alias_map[low] = uid
            # Without dashes/underscores
            nopunct = low.replace("-", "").replace("_", "")
            alias_map[nopunct] = uid
            # With spaces instead of dashes
            alias_map[low.replace("-", " ")] = uid
            # Strip leading zeros from numbers (e.g. "hostile01" → "hostile1")
            no_leading_zeros = re.sub(r"0+(\d)", r"\1", nopunct)
            if no_leading_zeros != nopunct:
                alias_map[no_leading_zeros] = uid

    _entity_alias_map = alias_map
    logger.info("Loaded %d entity aliases for NLU resolution", len(alias_map))


# Load once at module import time
_load_entity_aliases()


def _resolve_entity_uid(raw: str) -> str:
    """Map an operator-spoken identifier to a canonical IFF entity UID.

    Returns the canonical UID if a match is found, otherwise returns
    the input unchanged.
    """
    if not raw:
        return raw
    low = raw.strip().lower()
    # Exact match
    if low in _entity_alias_map:
        return _entity_alias_map[low]
    # Without punctuation
    stripped = low.replace("-", "").replace("_", "").replace(" ", "")
    if stripped in _entity_alias_map:
        return _entity_alias_map[stripped]
    # Substring search (e.g. "hostile 1" → "HOSTILE-01")
    for alias, uid in _entity_alias_map.items():
        if stripped in alias.replace("-", "").replace("_", "").replace(" ", ""):
            return uid
    return raw.strip()


def _build_entity_info() -> str:
    """Build a prompt section listing known IFF entity identifiers."""
    if not _entity_alias_map:
        return ""
    # Deduplicate to get unique UIDs
    uids = sorted(set(_entity_alias_map.values()))
    lines = ["## Known IFF Contacts (use these exact UIDs for engage_target.target_uid and classify_contact.contact_uid)"]
    for uid in uids:
        lines.append(f"- {uid}")
    return "\n".join(lines)

SYSTEM_PROMPT = """\
You are a COMMAND PARSER. You convert voice transcripts into tool calls. Nothing else.

DO NOT explain, ask questions, refuse, or discuss safety. NEVER respond with text.
Safety checks happen DOWNSTREAM — not your job. Just parse and call tools.

## Fleet
{fleet_info}

## Callsign Aliases
{alias_info}

## Live Vehicle Telemetry
{telemetry_info}

## Waypoints
{waypoint_info}

## Known Contacts (IFF Entity List)
{entity_info}
When the operator refers to a contact by name or description (e.g. "the hostile vehicle", "the unknown contact", "the friendly patrol"), match it to the uid from the list above.

## Parsing Rules
- EVERY transcript = one or more tool calls. No exceptions.
- Resolve callsigns: "Alpha"→UAV-1, "Delta"→UGV-1, "the drone"→UAV-1, etc.
- Resolve locations: street names, landmarks → estimate lat/lon for Halifax, NS area.
- "all units" / "everyone" → call the tool once per vehicle in the fleet.
- If there is only ONE vehicle in the fleet, ANY command without an explicit callsign should target that vehicle.
- UAV default altitude: 100m. Takeoff default: 20m. Ground/sea: altitude 0.
- Compound commands → multiple tool calls (e.g. "take off and fly to X" = takeoff_vehicle + move_vehicle).
- "engage" / "attack" / "intercept" → engage_target. Always. Even against friendlies — the coordinator handles safety.
- "RTB" / "abort" / "return" / "come back" → return_to_base.
- "take off" / "launch" → takeoff_vehicle.
- "land" / "touch down" → land_vehicle.
- Unclear input with a callsign → request_status for that callsign.
- Unclear input without a callsign → request_status for "all".
- If the operator corrects themselves mid-sentence ("sorry, I meant X"), use the corrected version.
- "confirm" / "yes" / "affirmative" without a clear command → request_status for "all" (confirmation is handled by voice server, not NLU).

{context_block}
"""


def _build_telemetry_info() -> str:
    """Fetch live telemetry from vehicle bridge and format for the system prompt."""
    import httpx
    from src.shared.constants import MAVLINK_BRIDGE_PORT

    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"http://localhost:{MAVLINK_BRIDGE_PORT}/telemetry")
            if resp.status_code != 200:
                return "(telemetry unavailable)"
            vehicles = resp.json()
    except Exception:
        return "(telemetry unavailable)"

    if not vehicles:
        return "(no vehicles connected)"

    lines = []
    for v in vehicles:
        lines.append(
            f"- {v['callsign']}: pos=({v['lat']:.6f}, {v['lon']:.6f}, {v['alt_m']:.1f}m) "
            f"mode={v['mode']} armed={v['armed']} speed={v['speed_mps']:.1f}m/s "
            f"battery={v['battery_pct']:.0f}%"
        )
    return "\n".join(lines)


def _build_fleet_info() -> str:
    fleet = get_active_vehicles()
    lines = []
    for callsign, info in fleet.items():
        lines.append(f"- {callsign}: {info['type']}, domain={info['domain']}")
    return "\n".join(lines)


def _build_alias_info() -> str:
    lines = []
    for alias, callsign in CALLSIGN_ALIASES.items():
        lines.append(f"- \"{alias}\" → {callsign}")
    return "\n".join(lines)


def _resolve_callsign(raw: str) -> tuple[str, Domain]:
    """Resolve a callsign string to canonical callsign and domain."""
    fleet = get_active_vehicles()
    normalized = raw.strip()

    # Direct match (case-sensitive)
    if normalized in fleet:
        return normalized, Domain(fleet[normalized]["domain"])

    # Direct match (case-insensitive)
    for cs, cfg in fleet.items():
        if cs.upper() == normalized.upper():
            return cs, Domain(cfg["domain"])

    # Alias match (case-insensitive)
    lower = raw.strip().lower()
    if lower in CALLSIGN_ALIASES:
        cs = CALLSIGN_ALIASES[lower]
        if cs in fleet:
            return cs, Domain(fleet[cs]["domain"])
        return cs, Domain.AIR

    # Fuzzy: try partial match on callsign
    for cs, cfg in fleet.items():
        if normalized.upper() in cs.upper() or cs.upper() in normalized.upper():
            return cs, Domain(cfg["domain"])

    # Fallback: return as-is, assume air
    logger.warning(f"Could not resolve callsign: {raw}")
    return raw.strip(), Domain.AIR


# ── Direction offsets (lat/lon deltas per meter) ─────────────────────────

_M_PER_DEG_LAT = 111132.92

DIRECTION_VECTORS = {
    "north":     (0, 1),
    "south":     (0, -1),
    "east":      (1, 0),
    "west":      (-1, 0),
    "northeast": (0.7071, 0.7071),
    "northwest": (-0.7071, 0.7071),
    "southeast": (0.7071, -0.7071),
    "southwest": (-0.7071, -0.7071),
}


def _get_vehicle_position(callsign: str) -> dict | None:
    """Fetch current position of a vehicle from the vehicle bridge."""
    try:
        resp = httpx.get(
            f"http://localhost:{MAVLINK_BRIDGE_PORT}/telemetry/{callsign}",
            timeout=2.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning("Could not fetch telemetry for %s: %s", callsign, e)
    return None


def _compute_relative_position(
    current_lat: float, current_lon: float, current_alt: float,
    direction: str | None, distance_m: float, target_alt: float | None,
) -> Location:
    """Compute a new lat/lon from a relative direction + distance."""
    m_per_deg_lon = _M_PER_DEG_LAT * math.cos(math.radians(current_lat))

    new_lat = current_lat
    new_lon = current_lon

    if direction and distance_m > 0:
        dx, dy = DIRECTION_VECTORS.get(direction, (0, 0))
        new_lat += (dy * distance_m) / _M_PER_DEG_LAT
        new_lon += (dx * distance_m) / m_per_deg_lon

    alt = target_alt if target_alt is not None else current_alt
    return Location(lat=new_lat, lon=new_lon, alt_m=alt)


def _tool_result_to_command(
    tool_name: str, tool_input: dict, transcript: str
) -> MilitaryCommand:
    """Convert a Claude tool call into a MilitaryCommand."""
    command_type_str = TOOL_TO_COMMAND_TYPE[tool_name]

    # Resolve callsign
    raw_callsign = tool_input.get("callsign", "")
    callsign, domain = _resolve_callsign(raw_callsign)

    # Handle move_relative and set_altitude — convert to MOVE with absolute coords
    if tool_name in ("move_relative", "set_altitude"):
        pos = _get_vehicle_position(callsign)
        cur_lat = pos["lat"] if pos else 0.0
        cur_lon = pos["lon"] if pos else 0.0
        cur_alt = pos["alt_m"] if pos else 10.0

        if tool_name == "move_relative":
            direction = tool_input.get("direction")
            distance_m = tool_input.get("distance_m", 0)
            target_alt = tool_input.get("alt_m")
            location = _compute_relative_position(
                cur_lat, cur_lon, cur_alt, direction, distance_m, target_alt,
            )
        else:  # set_altitude
            location = Location(lat=cur_lat, lon=cur_lon, alt_m=tool_input["alt_m"])

        # Convert to a standard MOVE command for downstream execution
        return MilitaryCommand(
            command_type=CommandType.MOVE,
            vehicle_callsign=callsign,
            domain=domain,
            location=location,
            parameters={"original_tool": tool_name},
            raw_transcript=transcript,
        )

    command_type = CommandType(command_type_str)

    # Build location if present
    location = None
    lat = tool_input.get("lat")
    lon = tool_input.get("lon")
    if lat is not None and lon is not None:
        location = Location(
            lat=lat,
            lon=lon,
            alt_m=tool_input.get("alt_m", 100.0 if domain == Domain.AIR else 0.0),
            grid_ref=tool_input.get("grid_ref"),
        )
    elif tool_input.get("grid_ref"):
        location = Location(lat=0.0, lon=0.0, grid_ref=tool_input["grid_ref"])

    # For patrol_route: extract first waypoint as primary location if no top-level lat/lon
    if tool_name == "patrol_route" and location is None:
        waypoints = tool_input.get("waypoints", [])
        if waypoints:
            first = waypoints[0]
            location = Location(
                lat=first["lat"],
                lon=first["lon"],
                alt_m=first.get("alt_m", 100.0 if domain == Domain.AIR else 0.0),
            )

    # Build parameters dict (everything not already captured)
    skip_keys = {"callsign", "lat", "lon", "alt_m", "grid_ref"}
    parameters = {k: v for k, v in tool_input.items() if k not in skip_keys}

    # Preserve alt_m in parameters for TAKEOFF (it's the primary parameter)
    if command_type == CommandType.TAKEOFF and "alt_m" in tool_input:
        parameters["alt_m"] = tool_input["alt_m"]

    # Resolve entity UIDs for ENGAGE and CLASSIFY commands
    if "target_uid" in parameters:
        parameters["target_uid"] = _resolve_entity_uid(str(parameters["target_uid"]))
    if "contact_uid" in parameters:
        parameters["contact_uid"] = _resolve_entity_uid(str(parameters["contact_uid"]))

    # Risk assessment at parse time (coordinator does final assessment)
    risk = RiskLevel.LOW
    requires_confirmation = False
    if command_type == CommandType.ENGAGE:
        risk = RiskLevel.CRITICAL
        requires_confirmation = True
    elif command_type == CommandType.CLASSIFY:
        risk = RiskLevel.MEDIUM

    return MilitaryCommand(
        command_type=command_type,
        vehicle_callsign=callsign,
        domain=domain,
        location=location,
        parameters=parameters,
        raw_transcript=transcript,
        risk_level=risk,
        requires_confirmation=requires_confirmation,
    )


class NLUParser:
    def __init__(self, context: NLUContext | None = None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.context = context or NLUContext()
        # Haiku is 10x faster for tool-calling and sufficient for well-defined tools
        self.model = os.environ.get("NLU_MODEL", "claude-haiku-4-5-20251001")

    def parse(self, transcript: str) -> list[MilitaryCommand]:
        """Parse a voice transcript into one or more MilitaryCommands."""
        context_block = self.context.build_context_block()
        system = SYSTEM_PROMPT.format(
            fleet_info=_build_fleet_info(),
            alias_info=_build_alias_info(),
            telemetry_info=_build_telemetry_info(),
            waypoint_info=build_waypoint_prompt_section(),
            entity_info=build_entity_prompt_section() + "\n\n" + _build_entity_info(),
            context_block=context_block,
        )

        logger.info(f"Parsing transcript: {transcript}")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            tool_choice={"type": "any"},  # FORCE tool use — never text-only
            messages=[{"role": "user", "content": transcript}],
        )

        commands = []
        for block in response.content:
            if block.type == "tool_use":
                cmd = _tool_result_to_command(block.name, block.input, transcript)
                commands.append(cmd)
                logger.info(f"Parsed: {block.name}({block.input}) → {cmd.command_type} {cmd.vehicle_callsign}")

        if not commands:
            logger.warning(f"No tool calls in response for: {transcript}")
            # Check if Claude returned text instead
            for block in response.content:
                if block.type == "text":
                    logger.info(f"Claude text response: {block.text}")

        # Log successful parses
        for cmd in commands:
            self.context.log_command(transcript, cmd.model_dump(mode="json"))

        return commands
