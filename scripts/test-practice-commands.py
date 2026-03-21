#!/usr/bin/env python3
"""Test the C2 system against the challenge practice commands.

Sends each practice command through NLU → Coordinator and reports results.
Requires NLU (:8002) and Coordinator (:8000) to be running.

Usage:
    python scripts/test-practice-commands.py
    BATTLESPACE_WAYPOINTS=data/compound/waypoints.json python scripts/test-practice-commands.py
"""

import json
import sys
import httpx

NLU_URL = "http://localhost:8002/parse"
COORDINATOR_URL = "http://localhost:8000/command"

# Practice commands from challenge/practice_commands.txt
PRACTICE_COMMANDS = [
    "Take off to 10 meters",
    "Fly north 50 meters",
    "Fly to the northwest watch tower",
    "Descend to 5 meters",
    "Fly east to the command building",
    "Climb to 12 meters and hover over the rooftop",
    "Fly to the fuel depot",
    "Report current position and altitude",
    "Fly south to the shipping containers",
    "Drop to 3 meters and enter the motor pool",
    "Go to the northeast tower at 15 meters altitude",
    "Head back to the landing pad",
    "Land",
    "Turn off the engines and self-destruct",
]

# Expected behaviors
EXPECTED = {
    "Fly to the fuel depot": "blocked",  # no-go zone
    "Turn off the engines and self-destruct": "rejected_or_status",  # invalid/unsupported
}


def main():
    client = httpx.Client(timeout=30.0)

    # Check services are up
    for name, url in [("NLU", "http://localhost:8002/health"), ("Coordinator", "http://localhost:8000/health")]:
        try:
            r = client.get(url)
            r.raise_for_status()
            print(f"  {name}: OK")
        except Exception as e:
            print(f"  {name}: FAILED ({e})")
            print(f"\nERROR: {name} service is not running. Start services first.")
            sys.exit(1)

    print(f"\n{'='*70}")
    print(f"Testing {len(PRACTICE_COMMANDS)} practice commands")
    print(f"{'='*70}\n")

    results = []

    for i, cmd_text in enumerate(PRACTICE_COMMANDS, 1):
        print(f"[{i:2d}] \"{cmd_text}\"")

        # Step 1: Parse through NLU
        try:
            nlu_resp = client.post(NLU_URL, json={"transcript": cmd_text})
            if nlu_resp.status_code != 200:
                print(f"     NLU: PARSE FAILED ({nlu_resp.status_code}: {nlu_resp.text[:100]})")
                results.append({"command": cmd_text, "status": "parse_failed", "pass": cmd_text in EXPECTED})
                print()
                continue

            commands = nlu_resp.json()
            for parsed_cmd in commands:
                cmd_type = parsed_cmd.get("command_type", "?")
                callsign = parsed_cmd.get("vehicle_callsign", "?")
                location = parsed_cmd.get("location")
                loc_str = ""
                if location:
                    loc_str = f" → ({location['lat']:.6f}, {location['lon']:.6f}, {location.get('alt_m', 0)}m)"
                print(f"     NLU: {cmd_type} {callsign}{loc_str}")

        except Exception as e:
            print(f"     NLU: ERROR ({e})")
            results.append({"command": cmd_text, "status": "error", "pass": False})
            print()
            continue

        # Step 2: Route each parsed command through Coordinator
        for parsed_cmd in commands:
            try:
                coord_resp = client.post(COORDINATOR_URL, json=parsed_cmd)
                coord_data = coord_resp.json()
                status = coord_data.get("status", "unknown")
                reason = coord_data.get("reason", "")
                risk = coord_data.get("risk_level", "")

                status_str = status
                if reason:
                    status_str += f" — {reason}"
                if risk:
                    status_str += f" [risk={risk}]"
                print(f"     COORD: {status_str}")

                # Check expected behaviors
                expected = EXPECTED.get(cmd_text)
                passed = True
                if expected == "blocked" and status != "blocked":
                    passed = False
                    print(f"     FAIL: Expected BLOCKED but got {status}")
                elif expected == "blocked" and status == "blocked":
                    print(f"     PASS: Correctly blocked by no-go zone")

                results.append({
                    "command": cmd_text,
                    "status": status,
                    "pass": passed,
                })

            except Exception as e:
                print(f"     COORD: ERROR ({e})")
                results.append({"command": cmd_text, "status": "error", "pass": False})

        print()

    # Summary
    print(f"{'='*70}")
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    blocked = sum(1 for r in results if r["status"] == "blocked")
    executed = sum(1 for r in results if r["status"] == "executed")
    confirmed = sum(1 for r in results if r["status"] == "confirmation_required")
    failed = sum(1 for r in results if not r["pass"])

    print(f"Results: {total} commands processed")
    print(f"  Executed:      {executed}")
    print(f"  Blocked:       {blocked}")
    print(f"  Confirmation:  {confirmed}")
    print(f"  Parse failed:  {sum(1 for r in results if r['status'] == 'parse_failed')}")
    print(f"  Errors:        {sum(1 for r in results if r['status'] == 'error')}")
    print(f"\n  Validation: {passed}/{total} passed")
    if failed:
        print(f"  FAILURES: {failed}")
        for r in results:
            if not r["pass"]:
                print(f"    - \"{r['command']}\" → {r['status']}")
    print(f"{'='*70}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
