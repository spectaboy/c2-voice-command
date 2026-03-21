#!/usr/bin/env python3
"""
Utility: Stream live telemetry via pymavlink multicast.
Useful for verifying the connection and monitoring flight.
"""

import math
import time
from pymavlink import mavutil


def main():
    print("Connecting via multicast...")
    mav = mavutil.mavlink_connection("mcast:")
    mav.wait_heartbeat(timeout=15)
    print(f"Connected to system {mav.target_system}\n")

    mav.mav.request_data_stream_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)

    print("Streaming telemetry (Ctrl+C to stop)...\n")

    while True:
        msg = mav.recv_match(
            type=["GLOBAL_POSITION_INT", "ATTITUDE", "SYS_STATUS", "HEARTBEAT"],
            blocking=True, timeout=2)
        if not msg:
            continue

        mtype = msg.get_type()
        if mtype == "GLOBAL_POSITION_INT":
            print(f"[POS] lat={msg.lat/1e7:.6f} lon={msg.lon/1e7:.6f} "
                  f"alt={msg.relative_alt/1000:.1f}m hdg={msg.hdg/100:.0f}°")
        elif mtype == "ATTITUDE":
            print(f"[ATT] roll={math.degrees(msg.roll):.1f}° "
                  f"pitch={math.degrees(msg.pitch):.1f}° "
                  f"yaw={math.degrees(msg.yaw):.1f}°")
        elif mtype == "SYS_STATUS":
            print(f"[BAT] {msg.voltage_battery/1000:.1f}V {msg.battery_remaining}%")
        elif mtype == "HEARTBEAT" and msg.get_srcSystem() == mav.target_system:
            mode = mavutil.mode_string_v10(msg)
            armed = "ARMED" if msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED else "DISARMED"
            print(f"[MODE] {mode} | {armed}")


if __name__ == "__main__":
    main()
