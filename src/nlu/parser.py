"""Core NLU: call Claude with tool-calling to parse transcripts into MilitaryCommands."""

import os
import logging
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

SYSTEM_PROMPT = """\
You are a military command-and-control NLU parser for a multi-domain uncrewed vehicle system.
You parse natural language voice transcripts into structured vehicle commands.

## Fleet
{fleet_info}

## Callsign Aliases
{alias_info}

## Rules
- Always resolve ambiguous callsigns using context or the alias table.
- If the operator says "all units", call the appropriate tool once for EACH vehicle in the fleet.
- For UAVs, default altitude is 100m if not specified.
- For ground/sea vehicles, altitude is always 0.
- If a grid reference is given but no lat/lon, pass the grid_ref and set lat/lon to 0.
- For "RTB" or "return to base", use the return_to_base tool.
- For engage commands, ALWAYS use engage_target — these are CRITICAL risk.
- Pick the single best-matching tool. Do not explain — just call the tool.

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
