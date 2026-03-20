import asyncio
import logging
import time
from typing import Optional

from pymavlink import mavutil

from src.shared.schemas import VehicleStatus, Domain, Affiliation

logger = logging.getLogger(__name__)

# MAVLink mode mappings for ArduPilot
COPTER_MODES = {
    "STABILIZE": 0, "ACRO": 1, "ALT_HOLD": 2, "AUTO": 3,
    "GUIDED": 4, "LOITER": 5, "RTL": 6, "CIRCLE": 7,
    "LAND": 9, "DRIFT": 11, "SPORT": 13, "POSHOLD": 16,
}
ROVER_MODES = {
    "MANUAL": 0, "ACRO": 1, "STEERING": 3, "HOLD": 4,
    "LOITER": 5, "FOLLOW": 6, "SIMPLE": 7, "AUTO": 10,
    "RTL": 11, "GUIDED": 15,
}

HEARTBEAT_TIMEOUT = 5.0


class MAVLinkClient:
    """Manages a single pymavlink connection to one ArduPilot SITL instance."""

    def __init__(
        self,
        callsign: str,
        host: str,
        port: int,
        sysid: int,
        vehicle_type: str,
        domain: str,
    ):
        self.callsign = callsign
        self.host = host
        self.port = port
        self.sysid = sysid
        self.vehicle_type = vehicle_type  # "ArduCopter" or "Rover"
        self.domain = domain
        self.conn: Optional[mavutil.mavfile] = None
        self._connected = False
        self._recv_task: Optional[asyncio.Task] = None

        # Cached telemetry
        self._lat = 0.0
        self._lon = 0.0
        self._alt_m = 0.0
        self._heading = 0.0
        self._speed_mps = 0.0
        self._battery_pct = 100.0
        self._mode = "UNKNOWN"
        self._armed = False
        self._last_heartbeat = 0.0

        self._affiliation = Affiliation.FRIENDLY

    @property
    def is_copter(self) -> bool:
        return self.vehicle_type == "ArduCopter"

    @property
    def mode_map(self) -> dict:
        return COPTER_MODES if self.is_copter else ROVER_MODES

    @property
    def connected(self) -> bool:
        if not self._connected:
            return False
        return (time.time() - self._last_heartbeat) < HEARTBEAT_TIMEOUT

    async def connect(self) -> None:
        """Open TCP connection to SITL and wait for first heartbeat."""
        addr = f"tcp:{self.host}:{self.port}"
        logger.info(f"[{self.callsign}] Connecting to {addr}")

        self.conn = await asyncio.to_thread(
            mavutil.mavlink_connection, addr, source_system=255
        )

        # Wait for heartbeat with timeout
        hb = await asyncio.to_thread(self.conn.wait_heartbeat, timeout=10)
        if hb is None:
            raise ConnectionError(
                f"[{self.callsign}] No heartbeat from {addr}"
            )

        self._last_heartbeat = time.time()
        self._connected = True
        logger.info(f"[{self.callsign}] Connected (sysid={self.sysid})")

        # Request data streams
        await self._request_data_streams()

        # Start background recv loop
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def disconnect(self) -> None:
        """Close the connection and stop the recv loop."""
        self._connected = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self.conn:
            self.conn.close()
            self.conn = None
        logger.info(f"[{self.callsign}] Disconnected")

    def get_status(self) -> VehicleStatus:
        """Return cached telemetry as a VehicleStatus object."""
        return VehicleStatus(
            uid=f"SITL-{self.callsign.replace('-', '-')}",
            callsign=self.callsign,
            domain=Domain(self.domain),
            affiliation=self._affiliation,
            lat=self._lat,
            lon=self._lon,
            alt_m=self._alt_m,
            heading=self._heading,
            speed_mps=self._speed_mps,
            battery_pct=self._battery_pct,
            mode=self._mode,
            armed=self._armed,
        )

    async def set_mode(self, mode: str) -> bool:
        """Change flight mode. Returns True on success."""
        mode = mode.upper()
        mode_id = self.mode_map.get(mode)
        if mode_id is None:
            logger.error(f"[{self.callsign}] Unknown mode: {mode}")
            return False

        if self.is_copter:
            custom_mode = mode_id
            base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        else:
            custom_mode = mode_id
            base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED

        await asyncio.to_thread(
            self.conn.set_mode, custom_mode
        )
        logger.info(f"[{self.callsign}] Mode → {mode}")
        return True

    async def arm(self, arm: bool = True) -> bool:
        """Arm or disarm the vehicle."""
        await asyncio.to_thread(
            self.conn.arducopter_arm if arm else self.conn.arducopter_disarm
        )
        logger.info(f"[{self.callsign}] {'Armed' if arm else 'Disarmed'}")
        return True

    async def takeoff(self, alt_m: float) -> bool:
        """Copter only: arm, set GUIDED mode, and takeoff to altitude."""
        if not self.is_copter:
            logger.warning(f"[{self.callsign}] Takeoff not supported for {self.vehicle_type}")
            return False

        await self.set_mode("GUIDED")
        await asyncio.sleep(0.5)
        await self.arm(True)
        await asyncio.sleep(0.5)

        await asyncio.to_thread(
            self.conn.mav.command_long_send,
            self.conn.target_system,
            self.conn.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,  # confirmation
            0, 0, 0, 0,  # params 1-4 unused
            0, 0,  # lat, lon (unused, current position)
            alt_m,  # param 7: altitude
        )
        logger.info(f"[{self.callsign}] Takeoff to {alt_m}m")
        return True

    async def move_to(self, lat: float, lon: float, alt: float) -> bool:
        """Send vehicle to a GPS position."""
        # Ensure we're in GUIDED mode
        if self._mode != "GUIDED":
            await self.set_mode("GUIDED")
            await asyncio.sleep(0.3)

        # If copter and not armed/airborne, takeoff first
        if self.is_copter and (not self._armed or self._alt_m < 1.0):
            await self.takeoff(alt if alt > 0 else 10.0)
            await asyncio.sleep(2.0)

        type_mask = (
            0b0000_1111_1111_1000  # ignore velocity, accel, yaw; use position only
        )

        await asyncio.to_thread(
            self.conn.mav.set_position_target_global_int_send,
            0,  # time_boot_ms
            self.conn.target_system,
            self.conn.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            type_mask,
            int(lat * 1e7),
            int(lon * 1e7),
            alt,
            0, 0, 0,  # velocity
            0, 0, 0,  # acceleration
            0, 0,     # yaw, yaw_rate
        )
        logger.info(f"[{self.callsign}] Move to ({lat:.6f}, {lon:.6f}, {alt}m)")
        return True

    async def land(self) -> bool:
        """Land at current position. Copters use LAND mode, rovers use HOLD."""
        if self.is_copter:
            return await self.set_mode("LAND")
        else:
            return await self.set_mode("HOLD")

    async def rtb(self) -> bool:
        """Return to base (set RTL mode)."""
        return await self.set_mode("RTL")

    # -- Internal --

    async def _request_data_streams(self) -> None:
        """Ask SITL to send us telemetry at a reasonable rate."""
        await asyncio.to_thread(
            self.conn.mav.request_data_stream_send,
            self.conn.target_system,
            self.conn.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            4,  # 4 Hz
            1,  # start
        )

    async def _recv_loop(self) -> None:
        """Background loop: read MAVLink messages and update cached telemetry."""
        while self._connected:
            try:
                msg = await asyncio.to_thread(
                    self.conn.recv_match, blocking=True, timeout=1.0
                )
                if msg is None:
                    continue

                msg_type = msg.get_type()

                if msg_type == "GLOBAL_POSITION_INT":
                    self._lat = msg.lat / 1e7
                    self._lon = msg.lon / 1e7
                    self._alt_m = msg.relative_alt / 1000.0
                    self._heading = msg.hdg / 100.0

                elif msg_type == "VFR_HUD":
                    self._speed_mps = msg.groundspeed
                    self._heading = msg.heading

                elif msg_type == "BATTERY_STATUS":
                    if msg.battery_remaining >= 0:
                        self._battery_pct = float(msg.battery_remaining)

                elif msg_type == "HEARTBEAT":
                    self._last_heartbeat = time.time()
                    self._armed = bool(
                        msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                    )
                    # Decode custom mode to name
                    mode_name = self._decode_mode(msg.custom_mode)
                    if mode_name:
                        self._mode = mode_name

            except Exception as e:
                if self._connected:
                    logger.warning(f"[{self.callsign}] recv error: {e}")
                    await asyncio.sleep(0.5)

    def _decode_mode(self, custom_mode: int) -> Optional[str]:
        """Reverse-lookup mode number to name."""
        for name, num in self.mode_map.items():
            if num == custom_mode:
                return name
        return None
