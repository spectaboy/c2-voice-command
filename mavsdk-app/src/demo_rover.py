#!/usr/bin/env python3
"""
Demo: Drive a rover through a waypoint mission.

Uses pymavlink over UDP multicast.
Requires: ./launch_gz.sh (terminal 1), ./launch_sitl.sh rover (terminal 2).
"""

import time
from pymavlink import mavutil


def connect():
    print("Connecting via multicast...")
    mav = mavutil.mavlink_connection("mcast:")
    mav.wait_heartbeat(timeout=15)
    print(f"  Connected to system {mav.target_system}")
    return mav


def wait_gps(mav):
    print("Waiting for GPS fix...")
    while True:
        msg = mav.recv_match(type="GPS_RAW_INT", blocking=True, timeout=5)
        if msg and msg.fix_type >= 3:
            print(f"  GPS OK")
            return


def get_home(mav):
    msg = mav.recv_match(type="GPS_RAW_INT", blocking=True, timeout=5)
    return msg.lat / 1e7, msg.lon / 1e7


def upload_mission(mav, waypoints):
    print(f"-- Uploading mission ({len(waypoints)} waypoints)")
    mav.waypoint_count_send(len(waypoints))

    for i, (lat, lon) in enumerate(waypoints):
        msg = mav.recv_match(type=["MISSION_REQUEST", "MISSION_REQUEST_INT"],
                             blocking=True, timeout=10)
        if not msg:
            print(f"  No request for waypoint {i}")
            return False

        mav.mav.mission_item_int_send(
            mav.target_system, mav.target_component,
            i, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            0, 1, 0, 0, 0, 0,
            int(lat * 1e7), int(lon * 1e7), 0)
        print(f"  WP {i}: {lat:.6f}, {lon:.6f}")

    ack = mav.recv_match(type="MISSION_ACK", blocking=True, timeout=10)
    if ack and ack.type == 0:
        print("  Mission uploaded!")
        return True
    print(f"  Upload failed: {ack}")
    return False


def main():
    mav = connect()
    wait_gps(mav)

    home_lat, home_lon = get_home(mav)
    print(f"  Home: {home_lat:.6f}, {home_lon:.6f}")

    offset = 0.0004  # ~40m
    waypoints = [
        (home_lat + offset, home_lon),
        (home_lat + offset, home_lon + offset),
        (home_lat, home_lon + offset),
        (home_lat, home_lon),
    ]

    print("-- Arming")
    mav.arducopter_arm()
    mav.motors_armed_wait()

    upload_mission(mav, waypoints)

    print("-- Starting mission (AUTO mode)")
    mode_id = mav.mode_mapping().get("AUTO")
    mav.set_mode(mode_id)

    print("-- Monitoring...")
    while True:
        msg = mav.recv_match(type="MISSION_CURRENT", blocking=True, timeout=5)
        if msg:
            print(f"  Current waypoint: {msg.seq}")
        reached = mav.recv_match(type="MISSION_ITEM_REACHED", blocking=False)
        if reached:
            print(f"  Reached: {reached.seq}")
        hb = mav.recv_match(type="HEARTBEAT", blocking=False)
        if hb:
            mode = mavutil.mode_string_v10(hb)
            if mode not in ("AUTO", "INITIALISING"):
                print(f"  Mission complete (mode={mode})")
                break
        time.sleep(1)

    print("Done!")


if __name__ == "__main__":
    main()
