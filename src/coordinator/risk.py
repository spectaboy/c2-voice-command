"""Risk assessment engine for military commands."""

from typing import Optional

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


_AFFILIATION_LABELS = {
    "f": "FRIENDLY",
    "h": "HOSTILE",
    "u": "UNKNOWN",
    "n": "NEUTRAL",
}


def generate_engage_readback(
    command: MilitaryCommand,
    iff_result: Optional[dict],
) -> str:
    """Generate readback text for ENGAGE that includes IFF classification.

    *iff_result* is the dict returned by the IFF engine's ``/contact/{uid}``
    endpoint, or ``None`` when the target is not tracked / IFF is offline.
    """
    target_uid = command.parameters.get("target_uid", "unknown target")
    risk_label = command.risk_level.value.upper()

    if iff_result is None:
        # IFF unavailable — warn operator
        return (
            f"CONFIRM: {risk_label} RISK. You are ordering {command.vehicle_callsign} "
            f"to ENGAGE {target_uid}. WARNING: IFF status unavailable — target "
            f"classification could not be verified. "
            f"Say CONFIRM to execute or CANCEL to abort."
        )

    affiliation_code = iff_result.get("affiliation", "u")
    affiliation_label = _AFFILIATION_LABELS.get(affiliation_code, "UNKNOWN")
    threat_score = iff_result.get("threat_score")
    confidence = iff_result.get("confidence")
    indicators = iff_result.get("indicators", [])

    # Build threat detail string
    threat_detail = ""
    if threat_score is not None:
        threat_detail += f" Threat score: {threat_score:.2f}."
    if confidence is not None:
        threat_detail += f" Confidence: {confidence:.2f}."
    if indicators:
        indicator_str = "; ".join(indicators[:3])  # Cap at 3 for readback brevity
        threat_detail += f" Indicators: {indicator_str}."

    if affiliation_code == "h":
        return (
            f"CONFIRM: {risk_label} RISK. You are ordering {command.vehicle_callsign} "
            f"to ENGAGE HOSTILE target {target_uid}.{threat_detail} "
            f"Say CONFIRM to execute or CANCEL to abort."
        )

    # Unknown / neutral
    return (
        f"CONFIRM: {risk_label} RISK. You are ordering {command.vehicle_callsign} "
        f"to ENGAGE {affiliation_label} target {target_uid}.{threat_detail} "
        f"Say CONFIRM to execute or CANCEL to abort."
    )
