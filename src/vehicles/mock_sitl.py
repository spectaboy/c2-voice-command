"""
Mock SITL simulator — pure Python, no WSL needed.

Spawns 6 fake ArduPilot vehicles that speak MAVLink over TCP.
Uses raw sockets + pymavlink MAVLink framing (the tcpin: mode is broken).

Usage:
    python -m src.vehicles.mock_sitl
"""

import math
import socket
import threading
import time
import logging

from pymavlink import mavutil
from pymavlink.dialects.v10.ardupilotmega import MAVLink

from src.shared.battlespace import load_fleet

logger = logging.getLogger(__name__)

# Halifax Harbor — forward operating base
HOME_LAT = 44.6488
HOME_LON = -63.5752

# Slight offsets so vehicles don't stack on top of each other
VEHICLE_OFFSETS = {
    "Alpha": (0.0000,  0.0000),
    "Bravo": (0.0003,  0.0003),
    # Legacy 6-vehicle offsets
    "UAV-1": (0.0000,  0.0000),
    "UAV-2": (0.0005,  0.0005),
    "UAV-3": (0.0005, -0.0005),
    "UGV-1": (-0.0005, 0.0003),
    "UGV-2": (-0.0005, -0.0003),
    "USV-1": (-0.0010, 0.0000),
}


class SocketFile:
    """File-like wrapper around a socket for pymavlink's MAVLink class."""
    def __init__(self, sock):
        self.sock = sock

    def write(self, data):
        self.sock.sendall(data)

    def read(self, n):
        return self.sock.recv(n)


class MockVehicle:
    """Simulates one ArduPilot vehicle on a TCP port."""

    def __init__(self, callsign: str, port: int, sysid: int, vehicle_type: str, domain: str):
        self.callsign = callsign
        self.port = port
        self.sysid = sysid
        self.vehicle_type = vehicle_type
        self.domain = domain

        offset = VEHICLE_OFFSETS.get(callsign, (0, 0))
        self.lat = HOME_LAT + offset[0]
        self.lon = HOME_LON + offset[1]
        self.alt_m = 0.0
        self.heading = 0.0
        self.speed = 0.0
        self.battery = 100.0
        self.armed = False
        self.mode = 0  # STABILIZE for copter, MANUAL for rover

        self.target_lat = None
        self.target_lon = None
        self.target_alt = None

        self._running = False

    @property
    def is_copter(self):
        return self.vehicle_type == "ArduCopter"

    def start(self):
        self._running = True
        t = threading.Thread(target=self._run_server, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _run_server(self):
        """TCP server: accept clients in a loop."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Do NOT set SO_REUSEADDR on Windows — it allows multiple processes
        # to bind the same port, causing silent connection routing failures.
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            srv.bind(("0.0.0.0", self.port))
        except OSError as e:
            logger.error(f"[{self.callsign}] Cannot bind port {self.port}: {e}")
            return
        srv.listen(1)
        srv.settimeout(2.0)
        logger.info(f"[{self.callsign}] Listening on tcp:0.0.0.0:{self.port}")

        while self._running:
            try:
                conn, addr = srv.accept()
                logger.info(f"[{self.callsign}] Client connected from {addr}")
                self._handle_client(conn)
                logger.info(f"[{self.callsign}] Client disconnected, re-listening...")
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    logger.warning(f"[{self.callsign}] Accept error, retrying...")
                    time.sleep(1)

        srv.close()

    def _handle_client(self, conn: socket.socket):
        """Serve one connected client with MAVLink telemetry."""
        conn.settimeout(0.05)
        sockfile = SocketFile(conn)
        mav = MAVLink(sockfile, srcSystem=self.sysid, srcComponent=1)

        # For parsing incoming messages
        recv_mav = MAVLink(None, srcSystem=255, srcComponent=0)
        recv_mav.robust_parsing = True

        last_hb = 0.0
        last_telem = 0.0

        while self._running:
            now = time.time()

            try:
                # Heartbeat at 1 Hz (immediate on first loop)
                if now - last_hb >= 1.0:
                    self._send_heartbeat(mav)
                    last_hb = now

                # Telemetry at 10 Hz
                if now - last_telem >= 0.1:
                    self._update_physics(0.1)
                    self._send_telemetry(mav)
                    last_telem = now

                # Read incoming commands
                try:
                    data = conn.recv(4096)
                    if not data:
                        break  # Client gone
                    msgs = recv_mav.parse_buffer(data)
                    if msgs:
                        for msg in msgs:
                            self._handle_command(msg, mav)
                except socket.timeout:
                    pass

            except (ConnectionError, OSError):
                break

            time.sleep(0.01)

        try:
            conn.close()
        except Exception:
            pass

    def _send_heartbeat(self, mav):
        base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        if self.armed:
            base_mode |= mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED

        vtype = (
            mavutil.mavlink.MAV_TYPE_QUADROTOR
            if self.is_copter
            else mavutil.mavlink.MAV_TYPE_GROUND_ROVER
        )

        mav.heartbeat_send(
            type=vtype,
            autopilot=mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
            base_mode=base_mode,
            custom_mode=self.mode,
            system_status=mavutil.mavlink.MAV_STATE_ACTIVE,
        )

    def _send_telemetry(self, mav):
        # GLOBAL_POSITION_INT
        mav.global_position_int_send(
            time_boot_ms=int(time.time() * 1000) & 0xFFFFFFFF,
            lat=int(self.lat * 1e7),
            lon=int(self.lon * 1e7),
            alt=int(self.alt_m * 1000),
            relative_alt=int(self.alt_m * 1000),
            vx=0, vy=0, vz=0,
            hdg=int(self.heading * 100),
        )

        # VFR_HUD
        mav.vfr_hud_send(
            airspeed=self.speed,
            groundspeed=self.speed,
            heading=int(self.heading),
            throttle=50 if self.armed else 0,
            alt=self.alt_m,
            climb=0.0,
        )

        # BATTERY_STATUS
        mav.battery_status_send(
            id=0,
            battery_function=0,
            type=0,
            temperature=2500,
            voltages=[4200, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF,
                      0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF],
            current_battery=100,
            current_consumed=0,
            energy_consumed=0,
            battery_remaining=int(self.battery),
        )

    def _handle_command(self, msg, mav):
        msg_type = msg.get_type()
        if msg_type == "BAD_DATA":
            return

        if msg_type == "SET_MODE":
            self.mode = msg.custom_mode
            logger.info(f"[{self.callsign}] Mode -> {self.mode}")

        elif msg_type == "COMMAND_LONG":
            cmd_id = msg.command

            if cmd_id == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                self.armed = msg.param1 == 1.0
                logger.info(f"[{self.callsign}] {'Armed' if self.armed else 'Disarmed'}")

            elif cmd_id == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
                self.armed = True
                self.target_alt = msg.param7
                logger.info(f"[{self.callsign}] Takeoff to {msg.param7}m")

            elif cmd_id == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
                self.mode = int(msg.param2)
                logger.info(f"[{self.callsign}] Mode -> {self.mode}")

            try:
                mav.command_ack_send(cmd_id, 0)
            except Exception:
                pass

        elif msg_type == "SET_POSITION_TARGET_GLOBAL_INT":
            self.target_lat = msg.lat_int / 1e7
            self.target_lon = msg.lon_int / 1e7
            self.target_alt = msg.alt
            logger.info(
                f"[{self.callsign}] Move to ({self.target_lat:.6f}, "
                f"{self.target_lon:.6f}, {self.target_alt}m)"
            )

    def _update_physics(self, dt: float):
        """Simple physics: move toward target, drain battery."""
        if self.armed:
            self.battery = max(0.0, self.battery - 0.002 * dt)

        rtl_mode = 6 if self.is_copter else 11
        land_mode = 9 if self.is_copter else 4  # LAND for copter, HOLD for rover
        if self.mode == rtl_mode:
            offset = VEHICLE_OFFSETS.get(self.callsign, (0, 0))
            self.target_lat = HOME_LAT + offset[0]
            self.target_lon = HOME_LON + offset[1]
            self.target_alt = 0.0 if not self.is_copter else 20.0

        # LAND mode: descend at 8m/s, disarm at ground
        if self.is_copter and self.mode == land_mode and self.armed:
            if self.alt_m > 0.3:
                self.alt_m = max(0.0, self.alt_m - 8.0 * dt)
                self.speed = 0.0
                self.target_lat = None
                self.target_lon = None
                self.target_alt = None
            else:
                self.alt_m = 0.0
                self.armed = False
                self.mode = 0  # STABILIZE
                logger.info(f"[{self.callsign}] Landed and disarmed")

        # Altitude only (takeoff) — climb at 10m/s
        if self.target_alt is not None and self.target_lat is None:
            diff = self.target_alt - self.alt_m
            if abs(diff) > 0.5:
                self.alt_m += math.copysign(min(10.0 * dt, abs(diff)), diff)
            else:
                self.alt_m = self.target_alt
                self.target_alt = None

        # Move toward target
        if self.target_lat is not None and self.target_lon is not None:
            dlat = self.target_lat - self.lat
            dlon = self.target_lon - self.lon
            dist = math.sqrt(dlat**2 + dlon**2) * 111320

            if dist > 1.0:
                self.heading = math.degrees(math.atan2(dlon, dlat)) % 360
                max_speed = 30.0 if self.is_copter else 15.0
                self.speed = min(max_speed, dist)
                move_m = min(max_speed * dt, dist)
                move_deg = move_m / 111320
                ratio = move_deg / max(math.sqrt(dlat**2 + dlon**2), 1e-10)
                self.lat += dlat * ratio
                self.lon += dlon * ratio

                if self.target_alt is not None:
                    alt_diff = self.target_alt - self.alt_m
                    if abs(alt_diff) > 0.5:
                        self.alt_m += math.copysign(min(10.0 * dt, abs(alt_diff)), alt_diff)
            else:
                self.speed = 0.0
                self.target_lat = None
                self.target_lon = None
                if self.target_alt is not None:
                    self.alt_m = self.target_alt
                    self.target_alt = None
                if self.mode == rtl_mode:
                    self.armed = False
                    if self.is_copter:
                        self.alt_m = 0.0


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    print("=" * 50)
    print("  Mock SITL Simulator (no WSL required)")
    print(f"  Location: Halifax Harbor ({HOME_LAT}, {HOME_LON})")
    print("=" * 50)
    print()

    fleet = load_fleet()
    vehicles = []
    for callsign, cfg in fleet.items():
        v = MockVehicle(
            callsign=callsign,
            port=cfg["sitl_port"],
            sysid=cfg["sysid"],
            vehicle_type=cfg["type"],
            domain=cfg["domain"],
        )
        v.start()
        vehicles.append(v)
        print(f"  {callsign:6s}  tcp:0.0.0.0:{cfg['sitl_port']}  ({cfg['type']})")

    print()
    print(f"  {len(vehicles)}/{len(fleet)} vehicles listening.")
    print("  Press Ctrl+C to stop.")
    print("=" * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping mock SITL...")
        for v in vehicles:
            v.stop()
        print("Done.")


if __name__ == "__main__":
    main()
