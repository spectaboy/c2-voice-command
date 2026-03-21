# C2 Voice Command — Operations Runbook

## 1. Startup (5 terminals)

### Terminal 1 — Gazebo (WSL)
```bash
gz sim -v4 -r iris_runway.sdf
```

### Terminal 2 — SITL Alpha (WSL)
```bash
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --console -I0 --sysid 1
```
Listens on **5760** (TCP), but `sim_vehicle.py` exposes MAVProxy on **5762** (+2 offset).

### Terminal 3 — SITL Bravo (WSL)
```bash
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --console -I1 --sysid 2
```
Listens on **5770** (TCP), MAVProxy on **5772**.

### Terminal 4 — C2 Services (PowerShell)
```powershell
$env:SITL_HOST="172.22.86.6"; python scripts/start_all.py
```
Wait for all 6 services to show `OK`. If any show `CRASH`, check the error and re-run.

### Terminal 5 — Dashboard
```bash
cd src/dashboard && npm run dev
```
Opens on http://localhost:3000.

### Environment Variables
| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Powers NLU (Claude tool-use parser) |
| `SITL_HOST` | Yes* | — | WSL IP for real SITL. Omit to use mock. |
| `WHISPER_DEVICE` | No | `auto` | `cuda` / `cpu` / `auto` |
| `WHISPER_MODEL` | No | `large-v3-turbo` (GPU) / `small` (CPU) | Whisper model size |

**WSL IP:** `172.22.86.6` — find yours with `hostname -I` in WSL.

---

## 2. Quick Reference

### Fleet (`data/fleet.json`)
| Callsign | SITL TCP port | SysID | Notes |
|---|---|---|---|
| Alpha | **5760** | 1 | SERIAL0 for instance `-I0` (default when running `arducopter` directly) |
| Bravo | **5770** | 2 | SERIAL0 for instance `-I1` |

**Why not 5762/5772?** Those are SERIAL1. With **direct** `arducopter` (no `sim_vehicle.py`), SERIAL1 is **not** opened unless you add **`-C tcp:0`**. Alternative: keep fleet at 5762/5772 and add `-C tcp:0` to both SITL command lines.

### Callsign Aliases
| Say this... | Resolves to |
|---|---|
| "alpha", "drone 1", "the first drone", "uav 1", "uav-1", "the drone" | Alpha |
| "bravo", "drone 2", "the second drone", "uav 2", "uav-2" | Bravo |

### Named Waypoints
| Name | Lat | Lon |
|---|---|---|
| Base | 44.6488 | -63.5752 |
| Citadel Hill | 44.6478 | -63.5802 |
| Halifax Harbor | 44.6425 | -63.5670 |
| Halifax Waterfront | 44.6460 | -63.5680 |
| Georges Island | 44.6380 | -63.5620 |
| Point Pleasant Park | 44.6230 | -63.5690 |
| HMC Dockyard | 44.6620 | -63.5880 |
| Downtown | 44.6480 | -63.5730 |

### Hostile / Unknown Contacts
| Callsign | Affiliation | Domain | Position |
|---|---|---|---|
| HOSTILE-01 | hostile | ground | 44.6550, -63.5600 |
| UNKNOWN-01 | unknown | ground | 44.6218, -63.5752 |
| UNKNOWN-02 | unknown | ground | 44.6640, -63.5680 |
| UNKNOWN-03 | unknown | ground | 44.6488, -63.5495 |

### Service Ports
| Port | Service |
|---|---|
| 8000 | Coordinator |
| 8001 | Voice ASR (Whisper) |
| 8002 | NLU Parser (Claude) |
| 8003 | Vehicle Bridge (MAVLink) |
| 8004 | IFF Engine |
| 8005 | WebSocket Hub |
| 3000 | Dashboard (React) |

---

## 3. Bug Fixes (Session 2026-03-21)

| # | Bug | File(s) | What Was Wrong | Fix |
|---|---|---|---|---|
| 1 | ENGAGE handler crashed | `src/vehicles/vehicle_manager.py:168` | No handler existed for `CommandType.ENGAGE` — fell through to unknown | Added case that reads `target_uid` from params, moves to target location |
| 2 | PATROL ignored waypoints | `src/nlu/parser.py:231`, `src/vehicles/vehicle_manager.py:146` | NLU didn't emit `waypoints` array; handler only checked `cmd.location` | NLU now emits `waypoints` in parameters; handler reads them first |
| 3 | LOITER didn't navigate | `src/vehicles/vehicle_manager.py:123` | LOITER set flight mode without moving to the requested location first | Now moves to location, then switches mode to LOITER |
| 4 | Dashboard showed "executed" prematurely | `src/voice/server.py:337` | Broadcast `executed` event after coordinator returned `awaiting_confirmation` | Only broadcast `executed` on `executed` / `confirmed_and_executed` status |
| 5 | NLU had no telemetry context | `src/nlu/parser.py:162` | System prompt didn't include live vehicle positions/modes | Added `_build_telemetry_info()` that fetches `/telemetry` from bridge |
| 6 | Compound commands raced | `src/voice/server.py:342` | All commands in a compound utterance fired simultaneously | Added `asyncio.sleep(2.0)` between sequential commands |

---

## 4. Voice Test Checklist

Run these **after all services are UP and both drones show in Gazebo**.

| # | Say This | Expected Behavior | Verify In |
|---|---|---|---|
| 1 | "Alpha take off" | Alpha arms, climbs to ~20 m | Gazebo: drone lifts off |
| 2 | "Bravo take off" | Bravo arms, climbs to ~20 m | Gazebo: second drone lifts |
| 3 | "Alpha move to Citadel Hill" | Alpha flies to 44.6478, -63.5802 | Dashboard: position updates |
| 4 | "Bravo loiter at Georges Island" | Bravo flies to Georges Island, switches to LOITER mode | Dashboard: mode = LOITER |
| 5 | "Alpha patrol between Citadel Hill and the Dockyard" | Alpha navigates to first waypoint | Dashboard: patrol route |
| 6 | "Alpha engage hostile one" | Alpha moves toward HOSTILE-01 position | Dashboard: shows engage action |
| 7 | "Alpha status" | TTS reads back position, mode, battery | Listen for spoken readback |
| 8 | "Alpha return to base" | Alpha flies back to Base waypoint | Gazebo: returns to start |
| 9 | "Alpha take off and move to the harbor" | Takeoff completes, **then** moves (not simultaneously) | Gazebo: sequential actions |

---

## 5. CLI Verification (curl)

Use these to test without a microphone.

### Parse a command through NLU
```bash
curl -X POST http://localhost:8002/parse \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Alpha move to Citadel Hill"}'
```

### Send a command to Coordinator
```bash
curl -X POST http://localhost:8000/command \
  -H "Content-Type: application/json" \
  -d '{"callsign": "Alpha", "command_type": "move_to", "location": {"lat": 44.6478, "lon": -63.5802, "alt_m": 50.0}}'
```

### Check vehicle telemetry
```bash
curl http://localhost:8003/telemetry
```

### Check service health
```bash
curl http://localhost:8000/health   # Coordinator
curl http://localhost:8001/health   # Voice
curl http://localhost:8002/health   # NLU
curl http://localhost:8003/health   # Vehicle Bridge
curl http://localhost:8004/health   # IFF
curl http://localhost:8005/health   # WebSocket Hub
```

---

## 6. macOS + real `arducopter` (no WSL)

### 6a. World: two visible drones (Alpha / Bravo)

This repo’s `worlds/compound_ops.sdf` includes **two** models:

| Include name   | Model URI                    | FDM UDP (Gazebo ↔ JSON SITL) | SITL instance | MAVLink TCP (fleet; SERIAL0) |
|----------------|------------------------------|------------------------------|---------------|------------------------------|
| `iris_alpha`   | `model://iris_with_ardupilot`   | **9002**                     | `-I0`         | **5760** (Alpha)             |
| `iris_bravo`   | `model://iris_with_ardupilot_2` | **9012**                     | `-I1`         | **5770** (Bravo)             |

`iris_with_ardupilot_2` is a copy of `iris_with_ardupilot` with `<fdm_port_in>9012</fdm_port_in>` so it matches ArduPilot’s JSON port rule **9002 + instance×10** for instance 1.

**Always start Gazebo from the project root** so `model://…` resolves (`./launch_gz.sh` sets `GZ_SIM_RESOURCE_PATH`). On some Mac setups you may still need a second terminal: `gz sim -g` for the GUI.

### 6b. Four terminals (dual drone + C2)

1. **Gazebo**
   ```bash
   cd /path/to/c2-voice-command
   ./launch_gz.sh
   ```
2. **Alpha SITL** (instance 0 → FDM 9002)
   ```bash
   cd /path/to/c2-voice-command/ardupilot
   source ../.venv/bin/activate   # or .venv311 for tooling; arducopter is the binary
   build/sitl/bin/arducopter \
     --model JSON --speedup 1 --slave 0 \
     --defaults Tools/autotest/default_params/copter.parm,Tools/autotest/default_params/gazebo-iris.parm \
     --sim-address 127.0.0.1 \
     -I0 --sysid 1 \
     --home 32.990,-106.975,1400,0
   ```
3. **Bravo SITL** (instance 1 → FDM 9012)
   ```bash
   cd /path/to/c2-voice-command/ardupilot
   source ../.venv/bin/activate
   build/sitl/bin/arducopter \
     --model JSON --speedup 1 --slave 0 \
     --defaults Tools/autotest/default_params/copter.parm,Tools/autotest/default_params/gazebo-iris.parm \
     --sim-address 127.0.0.1 \
     -I1 --sysid 2 \
     --home 32.990,-106.975,1400,0
   ```
4. **C2 backend** (after both SITLs are up; `data/fleet.json` uses SERIAL0 **5760 / 5770**)
   ```bash
   cd /path/to/c2-voice-command
   source .venv311/bin/activate
   SITL_HOST=127.0.0.1 BATTLESPACE_FLEET=data/fleet.json python scripts/start_all.py
   ```

**Order:** Gazebo → both `arducopter` processes → backend. If the bridge started before SITL: `curl -s -X POST http://localhost:8003/reconnect`.

**Gotchas:** Do not use `launch_sitl.sh` / `sim_vehicle.py` for this on macOS (MAVProxy issues). With **direct** `arducopter`, the bridge uses **SERIAL0** ports **5760 / 5770** (see `data/fleet.json`). Only one MAVLink client per port — don’t attach MAVProxy/QGC to the same port as the bridge. Keep `--home` the same on both instances; spacing is from `<pose>` in the SDF.

### 6c. Single drone (Alpha only)

One include / one `arducopter` **`-I0 --sysid 1`** is enough; use `data/fleet_one.json` (Alpha only) if you want to avoid Bravo connection errors.

---

## 7. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `start_all.py` kills SITL / bridge never connects | Script used to `kill -9` PIDs on 5760,5770,… (same ports as `arducopter`) | Fixed when `SITL_HOST` is set (skips killing SITL ports). Start backend **after** `arducopter`, or restart SITL after backend. |
| `/reconnect` still shows old fleet | Bridge loaded fleet only at process start | Use **`POST /reconnect`** after code update, or restart the Vehicle Bridge; set `BATTLESPACE_FLEET` **before** starting uvicorn / `start_all.py`. |
| `connected_vehicles: 0` | Direct `arducopter` has no SERIAL1 unless **`-C tcp:0`**; fleet uses **5760/5770** | Confirm `lsof -nP -iTCP:5760 -iTCP:5770 \| grep LISTEN`; `POST /reconnect`. Or use **5762/5772** in fleet **and** add `-C tcp:0` to both SITL cmds. |
| Bravo never connects | Only one `arducopter` or both `-I0` | Need **two** processes: **`-I0`** (5760) and **`-I1`** (5770). |
| Gazebo errors on `iris_with_ardupilot_2` | `GZ_SIM_RESOURCE_PATH` missing `ardupilot_gazebo/models` | Run **`./launch_gz.sh`** from repo root, not `gz sim` on a bare path only. |
| Two drones stack on same spot | Both SITL instances same pose | World uses offset poses (`iris_alpha` / `iris_bravo`); ensure both SITLs use the same `--home` as in §6b. |
| `SITL_HOST` set but bridge can't connect | WSL IP changed after reboot | Run `hostname -I` in WSL, update `$env:SITL_HOST` |
| Port already in use | Previous Python processes didn't clean up | `taskkill /F /IM python.exe` then re-run `start_all.py` |
| NLU returns 422 | Whisper misheard the command | Check `src/nlu/data/command_log.json` for the raw transcript, rephrase |
| Dashboard won't connect | WebSocket hub (8005) not running | Verify `start_all.py` shows WS Hub as UP |
| "No vehicles connected" | SITL instances not running or wrong port | Ensure Terminals 2+3 show `APM: ArduPilot Ready` before starting services |
| Drone doesn't move in Gazebo | **MAVLink OK ≠ sim bridge OK** — `connected_vehicles` is TCP to SITL; motion needs **JSON FDM** (UDP) between `arducopter --model JSON` and Gazebo `iris_*` plugins (**9002** / **9012**) | Start **Gazebo server first** (`./launch_gz.sh`), then **both** `arducopter` processes; confirm no `bind` errors on 9002. See §6b FDM column. |
| Two-ship collision at same POI | NLU emitted identical lat/lon for each callsign | **Voice path:** `apply_formation_separation` spreads E–W (~22 m slots) + small alt stagger (~7 m per slot) for commands in the **same parse batch**. Env: `FORMATION_SPACING_M`, `FORMATION_ALT_STAGGER_M`, or `FORMATION_SEPARATION=0` to disable. |
| `ANTHROPIC_API_KEY` error | Key not set or expired | `$env:ANTHROPIC_API_KEY="sk-..."` before running `start_all.py` |
| Compound command only runs first part | 2s delay may not be enough for slow SITL | Increase sleep in `server.py:344` or wait for first command to complete |
