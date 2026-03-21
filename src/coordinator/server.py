"""FastAPI Coordinator service — port 8000."""

import json
import logging
import math
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.shared.constants import COORDINATOR_PORT, VOICE_PORT, WS_PORT
from src.shared.schemas import CommandType, MilitaryCommand
from .risk import assess_risk, generate_readback, generate_engage_readback
from .confirmation import ConfirmationStore
from .router import lookup_iff, route_command

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── No-Go Zone Support ──────────────────────────────────────────────────────

def _load_no_go_zones() -> list[dict]:
    """Load no-go zones from BATTLESPACE_NO_GO_ZONES env var or default path."""
    path = os.environ.get(
        "BATTLESPACE_NO_GO_ZONES",
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "compound", "no_go_zones.json"),
    )
    if not os.path.isfile(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load no-go zones from %s: %s", path, e)
        return []


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in meters."""
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_no_go_zones(lat: float, lon: float, alt_m: float) -> str | None:
    """Return rejection reason if (lat, lon, alt) falls in a no-go zone, else None."""
    for zone in _no_go_zones:
        dist = _haversine_m(lat, lon, zone["lat"], zone["lon"])
        if dist <= zone["radius_m"]:
            alt_ceil = zone.get("alt_ceil_m")
            if alt_ceil is None:
                # Absolute no-go at all altitudes
                return f"Target location is within the {zone['name']} no-go zone."
            elif alt_m < alt_ceil:
                return (
                    f"Target location is within the {zone['name']} no-go zone "
                    f"(restricted below {alt_ceil}m AGL, commanded altitude: {alt_m}m)."
                )
    return None


_no_go_zones = _load_no_go_zones()

app = FastAPI(title="Coordinator", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
confirmations = ConfirmationStore()


class ConfirmRequest(BaseModel):
    confirmed: bool


async def _notify_confirmation(
    command_id: str,
    command_type: str,
    vehicle_callsign: str,
    risk_level: str,
    readback: str,
) -> None:
    """Trigger voice readback AND broadcast a confirmation_required WS event."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                f"http://localhost:{VOICE_PORT}/readback",
                json={"text": readback, "command_id": command_id},
            )
        except Exception as exc:
            logger.warning("Voice readback failed: %s", exc)

        try:
            await client.post(
                f"http://localhost:{WS_PORT}/broadcast",
                json={
                    "type": "confirmation_required",
                    "payload": {
                        "command_id": command_id,
                        "command_type": command_type,
                        "vehicle_callsign": vehicle_callsign,
                        "risk_level": risk_level,
                        "readback_text": readback,
                    },
                },
            )
        except Exception as exc:
            logger.warning("WS hub confirmation broadcast failed: %s", exc)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "coordinator", "port": COORDINATOR_PORT}


@app.post("/command")
async def handle_command(command: MilitaryCommand):
    """Accept a MilitaryCommand, assess risk, route or request confirmation.

    For ENGAGE commands, the IFF engine is consulted first:
    - FRIENDLY target -> BLOCKED (never routed)
    - UNKNOWN target  -> confirmation required
    - HOSTILE target   -> confirmation required
    - IFF unavailable  -> confirmation required
    """
    command = assess_risk(command)

    # -- IFF-aware ENGAGE gating --
    if command.command_type == CommandType.ENGAGE:
        target_uid = command.parameters.get("target_uid", "")
        iff_result = None
        if target_uid:
            iff_result = await lookup_iff(target_uid)

        affiliation = iff_result.get("affiliation", "u") if iff_result else "u"

        # BLOCK friendly targets
        if affiliation == "f":
            logger.warning("ENGAGE BLOCKED: target %s is FRIENDLY", target_uid)
            return {
                "status": "blocked",
                "command_id": command.command_id,
                "reason": f"Target {target_uid} is classified FRIENDLY. "
                          "ENGAGE on friendly assets is prohibited.",
                "target_uid": target_uid,
                "affiliation": "f",
            }

        # All ENGAGE commands require confirmation (hostile + unknown)
        command.requires_confirmation = True
        readback = generate_engage_readback(command, iff_result)
        command_id = confirmations.add(command, readback)
        logger.info(
            "ENGAGE confirmation required: target=%s affiliation=%s",
            target_uid, affiliation,
        )
        await _notify_confirmation(
            command_id, command.command_type.value,
            command.vehicle_callsign, command.risk_level.value, readback,
        )
        return {
            "status": "confirmation_required",
            "command_id": command_id,
            "readback": readback,
            "risk_level": command.risk_level.value,
            "target_uid": target_uid,
            "affiliation": affiliation,
        }

    # -- No-go zone validation for commands with a target location --
    if command.location and command.command_type in (
        CommandType.MOVE, CommandType.OVERWATCH, CommandType.PATROL, CommandType.LOITER,
    ):
        rejection = check_no_go_zones(
            command.location.lat, command.location.lon, command.location.alt_m,
        )
        if rejection:
            logger.warning("Command BLOCKED by no-go zone: %s", rejection)
            return {
                "status": "blocked",
                "command_id": command.command_id,
                "reason": f"Command rejected. {rejection}",
            }

    # -- Standard flow for non-ENGAGE commands --
    logger.info(
        f"Command: {command.command_type} {command.vehicle_callsign} "
        f"risk={command.risk_level} confirm={command.requires_confirmation}"
    )

    if command.requires_confirmation:
        readback = generate_readback(command)
        command_id = confirmations.add(command, readback)
        await _notify_confirmation(
            command_id, command.command_type.value,
            command.vehicle_callsign, command.risk_level.value, readback,
        )
        return {
            "status": "confirmation_required",
            "command_id": command_id,
            "readback": readback,
            "risk_level": command.risk_level.value,
        }

    # Execute immediately
    result = await route_command(command)
    return {
        "status": "executed",
        "command_id": command.command_id,
        "command_type": command.command_type.value,
        "vehicle_callsign": command.vehicle_callsign,
        "result": result,
    }


@app.post("/confirm/{command_id}")
async def confirm_command(command_id: str, req: ConfirmRequest):
    """Confirm or cancel a pending command."""
    if not req.confirmed:
        cancelled = confirmations.cancel(command_id)
        if not cancelled:
            raise HTTPException(status_code=404, detail="Command not found or expired")
        return {"status": "cancelled", "command_id": command_id}

    command = confirmations.confirm(command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found or expired")

    result = await route_command(command)
    return {
        "status": "confirmed_and_executed",
        "command_id": command_id,
        "command_type": command.command_type.value,
        "vehicle_callsign": command.vehicle_callsign,
        "result": result,
    }


@app.get("/status")
async def get_status():
    """Proxy status request to vehicle bridge."""
    from .router import route_command as _route
    from src.shared.schemas import CommandType, Domain

    status_cmd = MilitaryCommand(
        command_type=CommandType.STATUS,
        vehicle_callsign="all",
        domain=Domain.AIR,
    )
    return await _route(status_cmd)


@app.get("/pending")
async def list_pending():
    """List all pending confirmations (debug endpoint)."""
    return {"pending": confirmations.list_pending()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=COORDINATOR_PORT)
