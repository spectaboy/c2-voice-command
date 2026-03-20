"""Command routing to downstream services."""

import logging
from typing import Any

import httpx

from src.shared.constants import MAVLINK_BRIDGE_PORT, IFF_PORT, WS_PORT
from src.shared.schemas import CommandType, MilitaryCommand, WSMessage

logger = logging.getLogger(__name__)

VEHICLE_BRIDGE_URL = f"http://localhost:{MAVLINK_BRIDGE_PORT}"
IFF_ENGINE_URL = f"http://localhost:{IFF_PORT}"
WS_HUB_URL = f"http://localhost:{WS_PORT}"

# Commands that go to the vehicle bridge
VEHICLE_COMMANDS = {
    CommandType.MOVE,
    CommandType.RTB,
    CommandType.LOITER,
    CommandType.PATROL,
    CommandType.OVERWATCH,
    CommandType.TAKEOFF,
    CommandType.LAND,
}


async def route_command(command: MilitaryCommand) -> dict[str, Any]:
    """Route a validated command to the appropriate downstream service.

    Returns the response from the downstream service, or an error dict.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        result: dict[str, Any]

        if command.command_type in VEHICLE_COMMANDS:
            result = await _send_to_vehicle_bridge(client, command)

        elif command.command_type == CommandType.CLASSIFY:
            result = await _send_to_iff(client, command)

        elif command.command_type == CommandType.STATUS:
            result = await _get_status(client, command)

        elif command.command_type == CommandType.ENGAGE:
            # Engage goes to vehicle bridge (orbit/track the target)
            result = await _send_to_vehicle_bridge(client, command)

        else:
            result = {"error": f"Unknown command type: {command.command_type}"}

        # Broadcast command event to WebSocket hub
        await _broadcast_event(client, command, result)

        return result


async def _send_to_vehicle_bridge(
    client: httpx.AsyncClient, command: MilitaryCommand
) -> dict:
    try:
        resp = await client.post(
            f"{VEHICLE_BRIDGE_URL}/execute",
            json=command.model_dump(mode="json"),
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        logger.error("Vehicle bridge not reachable")
        return {"error": "vehicle_bridge_offline", "command_id": command.command_id}
    except httpx.HTTPStatusError as e:
        logger.error(f"Vehicle bridge error: {e.response.status_code}")
        return {"error": f"vehicle_bridge_{e.response.status_code}", "command_id": command.command_id}


_AFFILIATION_MAP = {
    "friendly": "f", "hostile": "h", "unknown": "u", "neutral": "n",
    "friend": "f", "enemy": "h", "foe": "h",
}


async def _send_to_iff(client: httpx.AsyncClient, command: MilitaryCommand) -> dict:
    try:
        raw_affil = command.parameters.get("new_affiliation", "u")
        affil = _AFFILIATION_MAP.get(raw_affil.lower(), raw_affil) if raw_affil else "u"
        payload = {
            "uid": command.parameters.get("contact_uid"),
            "new_affiliation": affil,
        }
        resp = await client.post(f"{IFF_ENGINE_URL}/manual-classify", json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        logger.error("IFF engine not reachable")
        return {"error": "iff_engine_offline", "command_id": command.command_id}
    except httpx.HTTPStatusError as e:
        logger.error(f"IFF engine error: {e.response.status_code}")
        return {"error": f"iff_engine_{e.response.status_code}", "command_id": command.command_id}


async def _get_status(client: httpx.AsyncClient, command: MilitaryCommand) -> dict:
    try:
        resp = await client.get(f"{VEHICLE_BRIDGE_URL}/telemetry")
        resp.raise_for_status()
        telemetry = resp.json()

        # Filter to specific vehicle if not "all"
        callsign = command.vehicle_callsign
        if callsign.lower() != "all":
            telemetry = [v for v in telemetry if v.get("callsign") == callsign]

        return {"status": "ok", "vehicles": telemetry}
    except httpx.ConnectError:
        logger.error("Vehicle bridge not reachable for status")
        return {"error": "vehicle_bridge_offline"}
    except httpx.HTTPStatusError as e:
        return {"error": f"vehicle_bridge_{e.response.status_code}"}


async def _broadcast_event(
    client: httpx.AsyncClient, command: MilitaryCommand, result: dict
):
    """Best-effort broadcast to WebSocket hub."""
    try:
        event = WSMessage(
            type="command_ack",
            payload={
                "command_id": command.command_id,
                "command_type": command.command_type.value,
                "vehicle_callsign": command.vehicle_callsign,
                "raw_transcript": command.raw_transcript,
                "result": result,
            },
        )
        await client.post(
            f"{WS_HUB_URL}/broadcast",
            json=event.model_dump(mode="json"),
        )
    except Exception:
        # Non-critical — dashboard just won't get the event
        logger.debug("WS hub broadcast failed (non-critical)")
