#!/usr/bin/env python3
"""
UxS Hackathon — Mission Scorer

Monitors drone telemetry via pymavlink, scores waypoint completion, penalizes no-go zone violations,
and produces a score report.

Usage:
    python challenge/scorer.py --team "<YOUR TEAM NAME HERE>"
"""

import argparse
import hashlib
import hmac
import json
import math
import signal
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pymavlink import mavutil
from challenge.config import (
    WAYPOINTS, WAYPOINTS_BY_NAME, NO_GO_ZONES,
    MAX_WAYPOINT_POINTS, TIME_BONUS_THRESHOLD, TIME_BONUS_RATE,
    MAX_TIME_BONUS, TIME_LIMIT_SECS,
    PYMAVLINK_CONNECTION, latlon_to_local, distance_2d,
)

SCORER_VERSION = "1.0.0"
HMAC_KEY = b"uxs-hack-2026-f7a3b9c1e2d4056819ab"


class TelemetryChain:
    def __init__(self):
        self.entries = []
        self.prev_hash = "0" * 64

    def append(self, lat, lon, alt, timestamp):
        entry = {
            "seq": len(self.entries),
            "t": round(timestamp, 3),
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "alt": round(alt, 2),
            "prev": self.prev_hash,
        }
        entry_bytes = json.dumps(entry, sort_keys=True).encode()
        entry["hash"] = hashlib.sha256(entry_bytes).hexdigest()
        self.prev_hash = entry["hash"]
        self.entries.append(entry)

    def save(self, path):
        with open(path, "w") as f:
            for entry in self.entries:
                f.write(json.dumps(entry, sort_keys=True) + "\n")


# ── Scorer ───────────────────────────────────────────────────────────────────

class Scorer:
    def __init__(self, team):
        self.team = team
        self.chain = TelemetryChain()
        self.waypoints_hit = {}
        self.nogo_accum = {}
        self.nogo_in_zone = {}
        self.start_time = None
        self.end_time = None
        self.running = True
        self.samples = 0

    def process_position(self, lat, lon, alt, t):
        self.chain.append(lat, lon, alt, t)
        self.samples += 1
        x, y = latlon_to_local(lat, lon)

        # Check waypoints
        for wp in WAYPOINTS:
            if wp.name in self.waypoints_hit:
                continue
            hdist = distance_2d(x, y, wp.x, wp.y)
            vdist = abs(alt - wp.alt_agl)
            if hdist < wp.radius and vdist < wp.alt_tolerance:
                self.waypoints_hit[wp.name] = t
                elapsed = t - self.start_time
                print(f"\033[92m  [+{wp.points:3d}] {wp.name:15s} at {elapsed:.1f}s\033[0m")

        # Check no-go zones
        for zone in NO_GO_ZONES:
            hdist = distance_2d(x, y, zone.x, zone.y)
            in_zone = hdist < zone.radius and alt < zone.alt_ceil
            if in_zone:
                if zone.name in self.nogo_in_zone:
                    dt = t - self.nogo_in_zone[zone.name]
                    self.nogo_accum[zone.name] = self.nogo_accum.get(zone.name, 0) + dt
                else:
                    print(f"\033[91m  [!!] ENTERED NO-GO: {zone.name}\033[0m")
                self.nogo_in_zone[zone.name] = t
            elif zone.name in self.nogo_in_zone:
                print(f"\033[93m  [--] Exited {zone.name}\033[0m")
                del self.nogo_in_zone[zone.name]

    def compute_score(self):
        elapsed = (self.end_time or time.time()) - self.start_time
        base = sum(WAYPOINTS_BY_NAME[n].points for n in self.waypoints_hit)

        time_bonus = 0
        if len(self.waypoints_hit) == len(WAYPOINTS):
            time_bonus = min(MAX_TIME_BONUS,
                             max(0, TIME_BONUS_THRESHOLD - elapsed) * TIME_BONUS_RATE)

        penalty = sum(
            self.nogo_accum.get(z.name, 0) * z.penalty_per_sec
            for z in NO_GO_ZONES
        )
        violations = [
            {"zone": z.name, "duration_s": round(self.nogo_accum.get(z.name, 0), 2),
             "penalty": round(self.nogo_accum.get(z.name, 0) * z.penalty_per_sec, 1)}
            for z in NO_GO_ZONES if self.nogo_accum.get(z.name, 0) > 0
        ]

        total = max(0, base + time_bonus - penalty)
        return {
            "team": self.team,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": round(elapsed, 1),
            "score": {
                "waypoints_completed": len(self.waypoints_hit),
                "waypoints_total": len(WAYPOINTS),
                "base_points": base,
                "time_bonus": round(time_bonus, 1),
                "nogo_penalty": round(-penalty, 1),
                "total": round(total, 1),
            },
            "waypoints": {
                n: round(t - self.start_time, 1)
                for n, t in sorted(self.waypoints_hit.items(), key=lambda kv: kv[1])
            },
            "violations": violations,
            "chain_length": len(self.chain.entries),
            "chain_head_hash": self.chain.prev_hash,
            "scorer_version": SCORER_VERSION,
        }

    def print_dashboard(self):
        elapsed = time.time() - self.start_time
        score = self.compute_score()
        sys.stdout.write("\033[2J\033[H")
        print("══════════════════════════════════════════════════════")
        print(f"  Scorer — Team: {self.team}   {elapsed:.0f}s / {TIME_LIMIT_SECS}s   [{self.samples} samples]")
        print("══════════════════════════════════════════════════════\n")

        for wp in WAYPOINTS:
            if wp.name in self.waypoints_hit:
                t = self.waypoints_hit[wp.name] - self.start_time
                print(f"  \033[92m[x] {wp.name:15s} +{wp.points:3d} @ {t:.0f}s\033[0m")
            else:
                print(f"  [ ] {wp.name:15s} +{wp.points:3d}")

        print()
        if score["violations"]:
            for v in score["violations"]:
                print(f"  \033[91m  {v['zone']:15s} {v['duration_s']:.1f}s  -{v['penalty']:.0f}\033[0m")
        print(f"\n  \033[1mScore: {score['score']['total']:.0f}\033[0m")
        print("\n  Ctrl+C to finalize.")

    def finalize(self):
        self.end_time = time.time()
        report = self.compute_score()
        report_json = json.dumps(report, sort_keys=True)
        report["hmac"] = hmac.new(HMAC_KEY, report_json.encode(), hashlib.sha256).hexdigest()

        score_path = f"score_{self.team}.json"
        with open(score_path, "w") as f:
            json.dump(report, f, indent=2)

        telem_path = f"telemetry_{self.team}.jsonl"
        self.chain.save(telem_path)

        print(f"\n\n  FINAL SCORE: {report['score']['total']:.0f}")
        print(f"  Waypoints: {report['score']['waypoints_completed']}/{report['score']['waypoints_total']}")
        print(f"  Saved: {score_path}, {telem_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="UxS Hackathon Scorer")
    parser.add_argument("--team", required=True)
    parser.add_argument("--connection", default=PYMAVLINK_CONNECTION,
                        help=f"pymavlink connection (default: {PYMAVLINK_CONNECTION})")
    args = parser.parse_args()

    scorer = Scorer(args.team)

    def on_sigint(sig, frame):
        scorer.running = False
    signal.signal(signal.SIGINT, on_sigint)

    print(f"Connecting to SITL via {args.connection} ...")
    mav = mavutil.mavlink_connection(args.connection)
    mav.wait_heartbeat()
    print(f"Connected (sysid {mav.target_system}). Waiting for GPS...\n")

    # Request position stream
    mav.mav.request_data_stream_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_POSITION, 10, 1)

    scorer.start_time = time.time()
    last_dash = 0

    while scorer.running:
        msg = mav.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
        if not msg:
            continue

        t = time.time()
        lat = msg.lat / 1e7
        lon = msg.lon / 1e7
        alt = msg.relative_alt / 1000.0

        scorer.process_position(lat, lon, alt, t)

        if t - last_dash > 2.0:
            scorer.print_dashboard()
            last_dash = t

        if t - scorer.start_time > TIME_LIMIT_SECS:
            print("\n  [TIME] Mission limit reached!")
            break

    scorer.finalize()


if __name__ == "__main__":
    main()
