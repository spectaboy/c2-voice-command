"""Risk assessment engine for military commands."""

from src.shared.schemas import CommandType, MilitaryCommand, RiskLevel

# Risk mapping: command type → base risk level
RISK_MAP = {
    CommandType.MOVE: RiskLevel.LOW,
    CommandType.LOITER: RiskLevel.LOW,
    CommandType.PATROL: RiskLevel.LOW,
    CommandType.OVERWATCH: RiskLevel.LOW,
    CommandType.STATUS: RiskLevel.LOW,
    CommandType.RTB: RiskLevel.MEDIUM,
    CommandType.CLASSIFY: RiskLevel.MEDIUM,
    CommandType.ENGAGE: RiskLevel.CRITICAL,
}

# Commands that require voice confirmation before execution
CONFIRMATION_REQUIRED = {RiskLevel.HIGH, RiskLevel.CRITICAL}


def assess_risk(command: MilitaryCommand) -> MilitaryCommand:
    """Evaluate command risk and set confirmation requirements.

    Mutates and returns the command with updated risk_level and requires_confirmation.
    """
    risk = RISK_MAP.get(command.command_type, RiskLevel.LOW)
    command.risk_level = risk
    command.requires_confirmation = risk in CONFIRMATION_REQUIRED
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
