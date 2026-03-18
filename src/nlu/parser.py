"""Core NLU: call Claude with tool-calling to parse transcripts into MilitaryCommands."""

import json
import os
import logging
import re
from pathlib import Path
from typing import Union

import anthropic

from src.shared.schemas import (
    CommandType,
    Domain,
    Location,
    MilitaryCommand,
    RiskLevel,
)
from src.shared.constants import VEHICLES, CALLSIGN_ALIASES
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
You are a military command-and-control NLU parser for a multi-domain uncrewed vehicle system.
You parse natural language voice transcripts into structured vehicle commands.

## Fleet
{fleet_info}

## Callsign Aliases
{alias_info}

## Area of Operations — Halifax, Nova Scotia (44.64°N, 63.57°W)
Known locations (use these coordinates when the operator names a place):
- Halifax Harbor / the harbor: 44.6425, -63.5670
- Citadel Hill / the citadel: 44.6478, -63.5802
- Brunswick Street: 44.6500, -63.5740
- Barrington Street: 44.6490, -63.5720
- HMC Dockyard / the dockyard: 44.6620, -63.5880
- Point Pleasant Park / the park: 44.6230, -63.5690
- Georges Island: 44.6380, -63.5620
- McNabs Island: 44.6190, -63.5340
- Halifax Waterfront / the waterfront: 44.6460, -63.5680
- Pier 21: 44.6390, -63.5660
- North End / north end: 44.6600, -63.5800
- South End / south end: 44.6300, -63.5750
- Bedford Basin / the basin: 44.6800, -63.6300
- Angus L. Macdonald Bridge / the bridge: 44.6630, -63.5630
- Dartmouth / across the harbor: 44.6650, -63.5590
- CFB Halifax: 44.6510, -63.5820
- Halifax Commons / the commons: 44.6510, -63.5840

If the operator names a place you recognize (street, landmark, area), resolve it to approximate lat/lon coordinates. You are operating in Halifax — use your geographic knowledge. ALWAYS call the tool even if you have to estimate coordinates. Never refuse a command just because exact coordinates weren't given.

## Rules
- Always resolve ambiguous callsigns using context or the alias table.
- If the operator says "all units", call the appropriate tool once for EACH vehicle in the fleet.
- For UAVs, default altitude is 100m if not specified.
- For ground/sea vehicles, altitude is always 0.
- If a grid reference is given but no lat/lon, pass the grid_ref and set lat/lon to 0.
- For "RTB" or "return to base", use the return_to_base tool.
- For engage commands, ALWAYS use engage_target — these are CRITICAL risk.
- Pick the single best-matching tool. Do not explain — just call the tool.
- IMPORTANT: ALWAYS call a tool. Never respond with just text. If unsure about coordinates, estimate them.

{entity_info}

{context_block}
"""


def _build_fleet_info() -> str:
    lines = []
    for callsign, info in VEHICLES.items():
        lines.append(f"- {callsign}: {info['type']}, domain={info['domain']}")
    return "\n".join(lines)


def _build_alias_info() -> str:
    lines = []
    for alias, callsign in CALLSIGN_ALIASES.items():
        lines.append(f"- \"{alias}\" → {callsign}")
    return "\n".join(lines)


def _resolve_callsign(raw: str) -> tuple[str, Domain]:
    """Resolve a callsign string to canonical callsign and domain."""
    normalized = raw.strip().upper()

    # Direct match
    if normalized in VEHICLES:
        return normalized, Domain(VEHICLES[normalized]["domain"])

    # Alias match (case-insensitive)
    lower = raw.strip().lower()
    if lower in CALLSIGN_ALIASES:
        cs = CALLSIGN_ALIASES[lower]
        return cs, Domain(VEHICLES[cs]["domain"])

    # Fuzzy: try partial match on callsign
    for cs in VEHICLES:
        if normalized in cs or cs in normalized:
            return cs, Domain(VEHICLES[cs]["domain"])

    # Fallback: return as-is, assume air
    logger.warning(f"Could not resolve callsign: {raw}")
    return raw.strip(), Domain.AIR


def _tool_result_to_command(
    tool_name: str, tool_input: dict, transcript: str
) -> MilitaryCommand:
    """Convert a Claude tool call into a MilitaryCommand."""
    command_type = CommandType(TOOL_TO_COMMAND_TYPE[tool_name])

    # Resolve callsign
    raw_callsign = tool_input.get("callsign", "")
    callsign, domain = _resolve_callsign(raw_callsign)

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

    # Build parameters dict (everything not already captured)
    skip_keys = {"callsign", "lat", "lon", "alt_m", "grid_ref"}
    parameters = {k: v for k, v in tool_input.items() if k not in skip_keys}

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
        self.model = os.environ.get("NLU_MODEL", "claude-sonnet-4-6")

    def parse(self, transcript: str) -> list[MilitaryCommand]:
        """Parse a voice transcript into one or more MilitaryCommands."""
        context_block = self.context.build_context_block()
        system = SYSTEM_PROMPT.format(
            fleet_info=_build_fleet_info(),
            alias_info=_build_alias_info(),
            entity_info=_build_entity_info(),
            context_block=context_block,
        )

        logger.info(f"Parsing transcript: {transcript}")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
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
