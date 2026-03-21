import asyncio
import logging
import os
from typing import Optional

from src.shared.schemas import MilitaryCommand, VehicleStatus, CommandType
from src.shared.constants import VEHICLES
from src.shared.battlespace import get_active_vehicles
from src.vehicles.mavlink_client import MAVLinkClient

logger = logging.getLogger(__name__)


class VehicleManager:
    """Manages all 6 SITL vehicle connections and routes commands."""

    def __init__(self, host: str = os.environ.get("SITL_HOST", "127.0.0.1")):
        self.host = host
        self._clients: dict[str, MAVLinkClient] = {}

        fleet = get_active_vehicles()
        for callsign, cfg in fleet.items():
            sitl_port = cfg["sitl_port"]
            # If sitl_port is a string (e.g. "mcast:"), use it as connection string directly
            connection_string = None
            if isinstance(sitl_port, str):
                connection_string = sitl_port
            self._clients[callsign] = MAVLinkClient(
                callsign=callsign,
                host=host,
                port=sitl_port if isinstance(sitl_port, int) else 0,
                sysid=cfg["sysid"],
                vehicle_type=cfg["type"],
                domain=cfg["domain"],
                connection_string=connection_string,
            )

    async def connect_all(self, retries: int = 5, delay: float = 3.0) -> dict[str, bool]:
        """Connect to all SITL instances with retry. Returns {callsign: success}."""
        results = {cs: False for cs in self._clients}

        for attempt in range(1, retries + 1):
            unconnected = {
                cs: cl for cs, cl in self._clients.items()
                if not cl.connected
            }
            if not unconnected:
                break

            logger.info(f"Connection attempt {attempt}/{retries} for {len(unconnected)} vehicles...")

            async def _connect_one(callsign: str, client: MAVLinkClient):
                try:
                    await client.connect()
                    results[callsign] = True
                except Exception as e:
                    logger.warning(f"[{callsign}] attempt {attempt} failed: {e}")

            await asyncio.gather(
                *[_connect_one(cs, cl) for cs, cl in unconnected.items()]
            )

            connected = sum(1 for v in results.values() if v)
            if connected == len(self._clients):
                break
            if attempt < retries:
                logger.info(f"Connected {connected}/{len(self._clients)}, retrying in {delay}s...")
                await asyncio.sleep(delay)

        connected = sum(1 for v in results.values() if v)
        logger.info(f"Connected {connected}/{len(self._clients)} vehicles")
        return results

    async def disconnect_all(self) -> None:
        """Disconnect all vehicles."""
        await asyncio.gather(
            *[cl.disconnect() for cl in self._clients.values()]
        )
        logger.info("All vehicles disconnected")

    def get_client(self, callsign: str) -> Optional[MAVLinkClient]:
        """Lookup a client by callsign."""
        return self._clients.get(callsign)

    def get_all_status(self) -> list[VehicleStatus]:
        """Return telemetry from all connected vehicles."""
        statuses = []
        for client in self._clients.values():
            if client.connected:
                statuses.append(client.get_status())
        return statuses

    @property
    def connected_count(self) -> int:
        return sum(1 for c in self._clients.values() if c.connected)

    async def execute_command(self, cmd: MilitaryCommand) -> dict:
        """Route a MilitaryCommand to the appropriate vehicle(s)."""
        callsign = cmd.vehicle_callsign.upper()

        # Handle "ALL" — fan out to every connected vehicle
        if callsign == "ALL":
            return await self._execute_all(cmd)

        client = self.get_client(cmd.vehicle_callsign)
        if client is None:
            return {"success": False, "error": f"Unknown vehicle: {cmd.vehicle_callsign}"}
        if not client.connected:
            return {"success": False, "error": f"{cmd.vehicle_callsign} is not connected"}

        return await self._execute_single(client, cmd)

    async def _execute_single(self, client: MAVLinkClient, cmd: MilitaryCommand) -> dict:
        """Execute a command on a single vehicle."""
        try:
            match cmd.command_type:
                case CommandType.MOVE:
                    if cmd.location is None:
                        return {"success": False, "error": "MOVE requires a location"}
                    await client.move_to(
                        cmd.location.lat, cmd.location.lon, cmd.location.alt_m
                    )
                    return {"success": True, "action": "move_to", "callsign": client.callsign}

                case CommandType.RTB:
                    await client.rtb()
                    return {"success": True, "action": "rtb", "callsign": client.callsign}

                case CommandType.LOITER:
                    # Navigate to location first, then switch to LOITER mode
                    if cmd.location:
                        alt = cmd.location.alt_m if cmd.location.alt_m > 0 else 12.0
                        await client.move_to(
                            cmd.location.lat, cmd.location.lon, alt
                        )
                    await client.set_mode("LOITER")
                    return {"success": True, "action": "loiter", "callsign": client.callsign}

                case CommandType.OVERWATCH:
                    if cmd.location is None:
                        return {"success": False, "error": "OVERWATCH requires a location"}
                    alt = cmd.location.alt_m if cmd.location.alt_m > 0 else 15.0
                    await client.move_to(
                        cmd.location.lat, cmd.location.lon, alt
                    )
                    return {"success": True, "action": "overwatch", "callsign": client.callsign}

                case CommandType.STATUS:
                    status = client.get_status()
                    return {"success": True, "action": "status", "status": status.model_dump()}

                case CommandType.PATROL:
                    # Use waypoints from parameters if available, fall back to location
                    waypoints = cmd.parameters.get("waypoints", [])
                    if waypoints:
                        first = waypoints[0]
                        alt = first.get("alt_m", 100.0 if client.is_copter else 0.0)
                        await client.move_to(first["lat"], first["lon"], alt)
                    elif cmd.location:
                        await client.move_to(
                            cmd.location.lat, cmd.location.lon, cmd.location.alt_m
                        )
                    return {"success": True, "action": "patrol", "callsign": client.callsign}

                case CommandType.TAKEOFF:
                    alt = cmd.parameters.get("alt_m", 20.0)
                    await client.takeoff(alt)
                    return {"success": True, "action": "takeoff", "callsign": client.callsign, "alt_m": alt}

                case CommandType.LAND:
                    await client.land()
                    return {"success": True, "action": "land", "callsign": client.callsign}

                case CommandType.ENGAGE:
                    target_uid = cmd.parameters.get("target_uid", "")
                    if cmd.location:
                        alt = cmd.location.alt_m if cmd.location.alt_m > 0 else 15.0
                        await client.move_to(
                            cmd.location.lat, cmd.location.lon, alt
                        )
                    await client.set_mode("CIRCLE")
                    return {
                        "success": True,
                        "action": "engage",
                        "callsign": client.callsign,
                        "target_uid": target_uid,
                    }

                case _:
                    return {"success": False, "error": f"Unsupported command type: {cmd.command_type}"}

        except Exception as e:
            logger.error(f"Command execution failed for {client.callsign}: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_all(self, cmd: MilitaryCommand) -> dict:
        """Fan out a command to all connected vehicles."""
        results = []
        tasks = []
        for client in self._clients.values():
            if client.connected:
                per_vehicle_cmd = cmd.model_copy(
                    update={"vehicle_callsign": client.callsign}
                )
                tasks.append(self._execute_single(client, per_vehicle_cmd))

        if not tasks:
            return {"success": False, "error": "No connected vehicles"}

        results = await asyncio.gather(*tasks)
        return {
            "success": all(r["success"] for r in results),
            "action": "all_units",
            "results": results,
        }
