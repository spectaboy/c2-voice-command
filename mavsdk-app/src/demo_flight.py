#!/usr/bin/env python3
"""
Demo: Arm, take off, fly a square pattern, and land.

Uses pymavlink over UDP multicast. Multiple scripts can connect simultaneously.
Requires: ./launch_gz.sh (terminal 1), ./launch_sitl.sh (terminal 2).
"""

import time
import math
from pymavlink import mavutil


def connect():
    print("Connecting via multicast...")
    mav = mavutil.mavlink_connection("mcast:")
    mav.wait_heartbeat(timeout=15)
    print(f"  Connected to system {mav.target_system}")
    mav.mav.request_data_stream_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    return mav


def wait_gps(mav):
    print("Waiting for GPS fix...")
    while True:
        msg = mav.recv_match(type="GPS_RAW_INT", blocking=True, timeout=5)
        if msg and msg.fix_type >= 3:
            print(f"  GPS OK (fix={msg.fix_type}, sats={msg.satellites_visible})")
            return


def set_mode(mav, mode_name):
    mode_id = mav.mode_mapping().get(mode_name)
    if mode_id is None:
        print(f"  Unknown mode: {mode_name}")
        print(f"  Available: {list(mav.mode_mapping().keys())}")
        return
    mav.set_mode(mode_id)
    print(f"  Mode → {mode_name}")


def arm(mav):
    print("-- Arming")
    mav.arducopter_arm()
    mav.motors_armed_wait()
    print("  Armed!")


def takeoff(mav, alt=10):
    print(f"-- Taking off to {alt}m")
    mav.mav.command_long_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, 0, alt)

    while True:
        msg = mav.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=3)
        if msg and msg.relative_alt / 1000.0 >= alt * 0.9:
            print(f"  Reached {msg.relative_alt / 1000.0:.1f}m")
            return


def goto_ned(mav, north, east, down, duration=8):
    """Send a position target in local NED frame."""
    print(f"  → N={north:.0f} E={east:.0f} D={down:.0f}")
    mav.mav.set_position_target_local_ned_send(
        0, mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b0000111111111000,  # position only
        north, east, down,
        0, 0, 0, 0, 0, 0, 0, 0)
    time.sleep(duration)


def land(mav):
    print("-- Landing")
    set_mode(mav, "LAND")
    while True:
        msg = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=5)
        if msg and not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            print("  Landed and disarmed!")
            return


def main():
    mav = connect()
    wait_gps(mav)

    set_mode(mav, "GUIDED")
    arm(mav)
    takeoff(mav, 10)

    print("-- Flying square pattern")
    side = 10.0
    alt = -10.0  # NED: negative = up
    goto_ned(mav, side, 0, alt)
    goto_ned(mav, side, side, alt)
    goto_ned(mav, 0, side, alt)
    goto_ned(mav, 0, 0, alt)

    land(mav)
    print("Done!")


if __name__ == "__main__":
    main()
