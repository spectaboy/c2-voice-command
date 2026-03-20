"""Risk assessment engine for military commands."""

import logging

import httpx

from src.shared.constants import IFF_PORT
from src.shared.schemas import CommandType, MilitaryCommand, RiskLevel

logger = logging.getLogger(__name__)

# Risk mapping: command type → base risk level
RISK_MAP = {
    CommandType.MOVE: RiskLevel.LOW,
    CommandType.LOITER: RiskLevel.LOW,
    CommandType.PATROL: RiskLevel.LOW,
    CommandType.OVERWATCH: RiskLevel.LOW,
    CommandType.STATUS: RiskLevel.LOW,
    CommandType.TAKEOFF: RiskLevel.LOW,
    CommandType.LAND: RiskLevel.LOW,
    CommandType.RTB: RiskLevel.MEDIUM,
    CommandType.CLASSIFY: RiskLevel.MEDIUM,
    CommandType.ENGAGE: RiskLevel.CRITICAL,
}

# Commands that require voice confirmation before execution
CONFIRMATION_REQUIRED = {RiskLevel.HIGH, RiskLevel.CRITICAL}

IFF_URL = f"http://localhost:{IFF_PORT}"


async def assess_risk(command: MilitaryCommand) -> MilitaryCommand:
    """Evaluate command risk and set confirmation requirements.

    Mutates and returns the command with updated risk_level and requires_confirmation.
    For ENGAGE commands, queries IFF to enforce safety:
      - friendly target → blocked
      - unknown target → CRITICAL + requires confirmation
      - hostile target → CRITICAL + requires confirmation
    """
    risk = RISK_MAP.get(command.command_type, RiskLevel.LOW)
    command.risk_level = risk
    command.requires_confirmation = risk in CONFIRMATION_REQUIRED

    # IFF safety gate for ENGAGE commands
    if command.command_type == CommandType.ENGAGE:
        target_uid = command.parameters.get("target_uid", "")
        if target_uid:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{IFF_URL}/check/{target_uid}")
                    if resp.status_code == 200:
                        iff_data = resp.json()
                        affiliation = iff_data.get("affiliation", "u")
                        if affiliation == "f":
                            # BLOCK: cannot engage friendly
                            command.parameters["_blocked"] = True
                            command.parameters["_block_reason"] = (
                                f"BLOCKED: {target_uid} is classified FRIENDLY. "
                                f"Engagement denied to prevent fratricide."
                            )
                            logger.warning("ENGAGE blocked: %s is FRIENDLY", target_uid)
                        elif affiliation == "u":
                            command.risk_level = RiskLevel.CRITICAL
                            command.requires_confirmation = True
                            logger.info("ENGAGE requires confirmation: %s is UNKNOWN", target_uid)
                        else:
                            # hostile — still requires confirmation
                            command.risk_level = RiskLevel.CRITICAL
                            command.requires_confirmation = True
                            logger.info("ENGAGE requires confirmation: %s is HOSTILE", target_uid)
            except Exception as e:
                logger.warning("IFF check failed for %s: %s — defaulting to CRITICAL+confirm", target_uid, e)

    return command


def generate_readback(command: MilitaryCommand) -> str:
    """Generate human-readable readback text for confirmation."""
    risk_label = command.risk_level.value.upper()

    if command.command_type == CommandType.ENGAGE:
        target = command.parameters.get("target_uid", "unknown target")
        return (
            f"CONFIRM: {risk_label} RISK. You are ordering {command.vehicle_callsign} "
            f"to ENGAGE {target}. Say CONFIRM to execute or CANCEL to abort."
        )

    if command.command_type == CommandType.CLASSIFY:
        contact = command.parameters.get("contact_uid", "unknown contact")
        affiliation = command.parameters.get("new_affiliation", "unknown")
        return (
            f"CONFIRM: {risk_label} RISK. Reclassify contact {contact} as "
            f"{affiliation.upper()}. Say CONFIRM to execute or CANCEL to abort."
        )

    # Generic readback for anything else that somehow needs confirmation
    loc = ""
    if command.location:
        loc = f" at ({command.location.lat:.4f}, {command.location.lon:.4f})"
    return (
        f"CONFIRM: {risk_label} RISK. {command.command_type.value.upper()} "
        f"{command.vehicle_callsign}{loc}. Say CONFIRM to execute or CANCEL to abort."
    )
