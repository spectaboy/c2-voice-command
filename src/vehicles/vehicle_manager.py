import asyncio
import logging
from typing import Optional

from src.shared.schemas import MilitaryCommand, VehicleStatus, CommandType
from src.shared.constants import VEHICLES
from src.vehicles.mavlink_client import MAVLinkClient

logger = logging.getLogger(__name__)


class VehicleManager:
    """Manages all 6 SITL vehicle connections and routes commands."""

    def __init__(self, host: str = "127.0.0.1"):
        self.host = host
        self._clients: dict[str, MAVLinkClient] = {}

        for callsign, cfg in VEHICLES.items():
            self._clients[callsign] = MAVLinkClient(
                callsign=callsign,
                host=host,
                port=cfg["sitl_port"],
                sysid=cfg["sysid"],
                vehicle_type=cfg["type"],
                domain=cfg["domain"],
            )

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all SITL instances in parallel. Returns {callsign: success}."""
        results = {}

        async def _connect_one(callsign: str, client: MAVLinkClient):
            try:
                await client.connect()
                results[callsign] = True
            except Exception as e:
                logger.error(f"Failed to connect {callsign}: {e}")
                results[callsign] = False

        await asyncio.gather(
            *[_connect_one(cs, cl) for cs, cl in self._clients.items()]
        )
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
                    await client.set_mode("LOITER")
                    return {"success": True, "action": "loiter", "callsign": client.callsign}

                case CommandType.OVERWATCH:
                    if cmd.location is None:
                        return {"success": False, "error": "OVERWATCH requires a location"}
                    alt = cmd.location.alt_m if cmd.location.alt_m > 0 else 50.0
                    await client.move_to(
                        cmd.location.lat, cmd.location.lon, alt
                    )
                    return {"success": True, "action": "overwatch", "callsign": client.callsign}

                case CommandType.STATUS:
                    status = client.get_status()
                    return {"success": True, "action": "status", "status": status.model_dump()}

                case CommandType.PATROL:
                    # Stretch goal — for now, move to first location
                    if cmd.location:
                        await client.move_to(
                            cmd.location.lat, cmd.location.lon, cmd.location.alt_m
                        )
                    return {"success": True, "action": "patrol", "callsign": client.callsign}

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
