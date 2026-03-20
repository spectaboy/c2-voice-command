"""FastAPI Coordinator service — port 8000."""

import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.shared.constants import COORDINATOR_PORT
from src.shared.schemas import MilitaryCommand
from .risk import assess_risk, generate_readback
from .confirmation import ConfirmationStore
from .router import route_command

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "coordinator", "port": COORDINATOR_PORT}


@app.post("/command")
async def handle_command(command: MilitaryCommand):
    """Accept a MilitaryCommand, assess risk, route or request confirmation."""
    command = await assess_risk(command)
    logger.info(
        f"Command: {command.command_type} {command.vehicle_callsign} "
        f"risk={command.risk_level} confirm={command.requires_confirmation}"
    )

    # IFF safety gate: blocked commands (e.g. engaging a friendly)
    if command.parameters.get("_blocked"):
        reason = command.parameters.get("_block_reason", "Command blocked by safety gate")
        logger.warning("Command BLOCKED: %s", reason)
        return {
            "status": "blocked",
            "command_id": command.command_id,
            "reason": reason,
        }

    if command.requires_confirmation:
        readback = generate_readback(command)
        command_id = confirmations.add(command, readback)
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
