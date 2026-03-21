import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.shared.schemas import MilitaryCommand, VehicleStatus
from src.shared.constants import MAVLINK_BRIDGE_PORT, FTS_COT_PORT, WS_PORT
from src.vehicles.vehicle_manager import VehicleManager
from src.vehicles.cot_generator import CoTGenerator
from src.vehicles.cot_sender import CoTSender

logger = logging.getLogger(__name__)

# Suppress httpx noise from telemetry broadcast loop
logging.getLogger("httpx").setLevel(logging.WARNING)

# Global instances
vehicle_manager: VehicleManager | None = None
cot_generator: CoTGenerator | None = None
cot_sender: CoTSender | None = None
telemetry_task: asyncio.Task | None = None
ws_clients: set[WebSocket] = set()
_http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global vehicle_manager, cot_generator, cot_sender, telemetry_task, _http_client

    logging.basicConfig(level=logging.INFO)

    vehicle_manager = VehicleManager()
    cot_generator = CoTGenerator()
    cot_sender = CoTSender(port=FTS_COT_PORT)
    _http_client = httpx.AsyncClient(timeout=2.0)

    # Connect to SITL instances
    await vehicle_manager.connect_all()

    # Connect to FreeTAKServer (non-blocking — may not be running)
    await cot_sender.connect()

    # Start telemetry broadcast loop
    telemetry_task = asyncio.create_task(_telemetry_loop())

    yield

    # Shutdown
    if telemetry_task:
        telemetry_task.cancel()
        try:
            await telemetry_task
        except asyncio.CancelledError:
            pass

    if _http_client:
        await _http_client.aclose()
    await cot_sender.disconnect()
    await vehicle_manager.disconnect_all()


app = FastAPI(title="Vehicle Bridge", lifespan=lifespan)


# -- REST endpoints --


@app.get("/health")
async def health():
    return {
        "service": "vehicle-bridge",
        "connected_vehicles": vehicle_manager.connected_count if vehicle_manager else 0,
        "cot_connected": cot_sender.connected if cot_sender else False,
    }


@app.post("/reconnect")
async def reconnect():
    """Reconnect to SITL instances that aren't connected."""
    if vehicle_manager is None:
        return {"success": False, "error": "Vehicle manager not initialized"}
    results = await vehicle_manager.connect_all(retries=3, delay=2.0)
    return {
        "success": True,
        "connected": vehicle_manager.connected_count,
        "results": results,
    }


@app.post("/execute")
async def execute_command(cmd: MilitaryCommand):
    if vehicle_manager is None:
        return {"success": False, "error": "Vehicle manager not initialized"}
    return await vehicle_manager.execute_command(cmd)


@app.get("/telemetry", response_model=list[VehicleStatus])
async def get_telemetry():
    if vehicle_manager is None:
        return []
    return vehicle_manager.get_all_status()


@app.get("/telemetry/{callsign}")
async def get_vehicle_telemetry(callsign: str):
    """Get telemetry for a single vehicle by callsign."""
    if vehicle_manager is None:
        raise HTTPException(status_code=503, detail="Vehicle manager not initialized")
    client = vehicle_manager.get_client(callsign)
    if client is None:
        raise HTTPException(status_code=404, detail=f"Unknown vehicle: {callsign}")
    status = client.get_status()
    return status.model_dump(mode="json")


class ReclassifyRequest(BaseModel):
    uid: str
    new_affiliation: str


@app.post("/reclassify")
async def reclassify(req: ReclassifyRequest):
    if cot_generator is None:
        return {"success": False, "error": "CoT generator not initialized"}
    cot_generator.update_affiliation(req.uid, req.new_affiliation)
    return {"success": True, "uid": req.uid, "affiliation": req.new_affiliation}


# -- WebSocket --


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    logger.info(f"WebSocket client connected ({len(ws_clients)} total)")
    try:
        while True:
            # Keep connection alive; client doesn't send data
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
        logger.info(f"WebSocket client disconnected ({len(ws_clients)} total)")


# -- Background telemetry loop --


async def _telemetry_loop():
    """4 Hz loop: broadcast telemetry via WebSocket and send CoT to FTS."""
    global ws_clients
    while True:
        try:
            await asyncio.sleep(0.25)

            if vehicle_manager is None:
                continue

            statuses = vehicle_manager.get_all_status()

            # Broadcast via WebSocket
            if ws_clients and statuses:
                payload = [s.model_dump(mode="json") for s in statuses]
                dead = set()
                for ws in ws_clients:
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.add(ws)
                ws_clients -= dead

            # Broadcast each vehicle status to the WebSocket Hub for the dashboard
            if statuses and _http_client:
                hub_url = f"http://localhost:{WS_PORT}/broadcast"
                try:
                    for status in statuses:
                        await _http_client.post(hub_url, json={
                            "type": "position_update",
                            "payload": status.model_dump(mode="json"),
                        })
                except Exception:
                    pass  # Hub may not be running

            # Send CoT to FreeTAKServer
            if cot_generator and cot_sender:
                for status in statuses:
                    xml = cot_generator.generate_cot_event(status)
                    await cot_sender.send(xml)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Telemetry loop error: {e}")
            await asyncio.sleep(1.0)


# -- Entry point --

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.vehicles.server:app",
        host="0.0.0.0",
        port=MAVLINK_BRIDGE_PORT,
        log_level="info",
    )
