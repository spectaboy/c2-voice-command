"""WebSocket Hub — port 8005.

Central aggregation point for all real-time events. Backend services POST
events here; the hub broadcasts them to all connected dashboard clients
via WebSocket.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any

from src.shared.constants import WS_PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WebSocket Hub", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connected WebSocket clients
_clients: set[WebSocket] = set()


class BroadcastMessage(BaseModel):
    type: str
    payload: dict[str, Any] = {}
    timestamp: datetime | None = None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "websocket-hub",
        "port": WS_PORT,
        "connected_clients": len(_clients),
    }


@app.post("/broadcast")
async def broadcast(msg: BroadcastMessage):
    """Accept an event from any backend service and broadcast to all WS clients."""
    if msg.timestamp is None:
        msg.timestamp = datetime.now(timezone.utc)

    payload = msg.model_dump(mode="json")
    dead: set[WebSocket] = set()

    for ws in _clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)

    _clients.difference_update(dead)

    logger.info(
        "Broadcast %s to %d clients (type=%s)",
        msg.type,
        len(_clients),
        msg.type,
    )
    return {"status": "ok", "clients_notified": len(_clients)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """Dashboard clients connect here to receive all real-time events."""
    await ws.accept()
    _clients.add(ws)
    logger.info("Dashboard client connected (%d total)", len(_clients))

    try:
        while True:
            # Read messages from client (e.g. confirmation responses)
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                # Forward confirmation responses to coordinator
                if msg_type == "confirm_command":
                    await _forward_confirmation(msg)
                elif msg_type == "cancel_command":
                    await _forward_cancellation(msg)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        logger.info("Dashboard client disconnected (%d remaining)", len(_clients))


async def _forward_confirmation(msg: dict):
    """Forward a confirmation from the dashboard to the coordinator."""
    import httpx
    command_id = msg.get("command_id", "")
    if not command_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"http://localhost:8000/confirm/{command_id}",
                json={"confirmed": True},
            )
    except Exception as e:
        logger.warning("Failed to forward confirmation: %s", e)


async def _forward_cancellation(msg: dict):
    """Forward a cancellation from the dashboard to the coordinator."""
    import httpx
    command_id = msg.get("command_id", "")
    if not command_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"http://localhost:8000/confirm/{command_id}",
                json={"confirmed": False},
            )
    except Exception as e:
        logger.warning("Failed to forward cancellation: %s", e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WS_PORT)
