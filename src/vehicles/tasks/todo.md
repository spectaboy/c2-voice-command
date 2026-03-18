# Vehicle Bridge — Implementation Plan

## Scope
`src/vehicles/` only. FastAPI service on port 8003.
Connects to 6 ArduPilot SITL instances, exposes REST/WebSocket API, generates CoT XML.

**Does NOT touch:** `src/shared/`, `src/voice/`, `src/nlu/`, `src/coordinator/`, `src/tak/`, `src/iff/`, `src/dashboard/`

---

## Phase 1: MAVLink Client — Single Vehicle Connection

- [x] **1.1** `src/vehicles/__init__.py`
- [x] **1.2** `src/vehicles/mavlink_client.py` — `MAVLinkClient` class
  - `__init__(callsign, host, port, sysid, vehicle_type)` — config only
  - `async connect()` — pymavlink TCP connection, wait for heartbeat
  - `async disconnect()` — close connection
  - `async get_status() -> VehicleStatus` — return cached telemetry
  - `async set_mode(mode)` — COMMAND_LONG mode change
  - `async arm(arm=True)` — COMMAND_LONG arm/disarm
  - `async takeoff(alt_m)` — copter only: arm + GUIDED + takeoff
  - `async move_to(lat, lon, alt)` — SET_POSITION_TARGET_GLOBAL_INT
  - `async rtb()` — set mode RTL
  - `_recv_loop()` — background task caching GLOBAL_POSITION_INT, HEARTBEAT, VFR_HUD, BATTERY_STATUS
  - Heartbeat timeout detection (>5s = lost)
  - pymavlink is sync — wrap in `asyncio.to_thread()`

## Phase 2: Vehicle Manager — Multi-Vehicle Orchestration

- [x] **2.1** `src/vehicles/vehicle_manager.py` — `VehicleManager` class
  - `__init__()` — reads VEHICLES config from shared constants
  - `async connect_all()` — parallel connect all 6
  - `async disconnect_all()` — graceful shutdown
  - `get_client(callsign) -> MAVLinkClient` — lookup
  - `async execute_command(cmd: MilitaryCommand) -> dict` — route by command_type:
    - MOVE → move_to (+ takeoff if copter not airborne)
    - RTB → set mode RTL
    - LOITER → set mode LOITER
    - OVERWATCH → move_to + loiter at altitude
    - STATUS → get_status
    - PATROL → waypoint sequence (stretch)
  - `async get_all_status() -> list[VehicleStatus]`
  - Handle callsign="ALL" → fan out to all vehicles

## Phase 3: CoT XML Generation & Sending

- [x] **3.1** `src/vehicles/cot_generator.py` — `CoTGenerator` class
  - `generate_cot_event(status: VehicleStatus) -> str` — build XML
    - `<event>` uid, type from COT_TYPES, how="m-g", time/start/stale
    - `<point>` lat, lon, hae, ce="5.0", le="5.0"
    - `<detail>` with `<contact>` and `<track>`
    - Stale = now + 30s, ISO 8601 UTC
  - `update_affiliation(uid, new_affiliation)` — update CoT type string
  - stdlib `xml.etree.ElementTree` only

- [x] **3.2** `src/vehicles/cot_sender.py` — `CoTSender` class
  - `async connect(host, port)` — TCP to FTS :8087
  - `async send(cot_xml: str)` — write bytes
  - `async disconnect()` — close
  - Auto-reconnect on loss

## Phase 4: FastAPI Server

- [x] **4.1** `src/vehicles/server.py` — FastAPI app on :8003
  - `POST /execute` — accept MilitaryCommand, route via VehicleManager
  - `GET /telemetry` — return all VehicleStatus objects
  - `GET /health` — connected vehicle count
  - `WebSocket /ws/telemetry` — stream positions at 1 Hz
  - `POST /reclassify` — accept `{uid, new_affiliation}` from IFF engine
  - Startup: connect VehicleManager + CoTSender
  - Shutdown: disconnect all

- [x] **4.2** Background telemetry loop (1 Hz)
  - get_all_status() → broadcast WebSocket + generate CoT → send to FTS

## Phase 5: Tests

- [x] **5.1** `tests/test_vehicles/__init__.py`
- [x] **5.2** `tests/test_vehicles/test_cot_generator.py`
  - Valid XML structure, correct type strings, ISO timestamps
  - Affiliation change updates type string
  - All 6 vehicle configs produce valid CoT
- [x] **5.3** `tests/test_vehicles/test_vehicle_manager.py`
  - Command routing (MOVE, RTB, LOITER, STATUS)
  - "ALL" callsign fan-out
  - Unknown callsign → error
  - Mock pymavlink
- [x] **5.4** `tests/test_vehicles/test_server.py`
  - FastAPI TestClient: /execute, /telemetry, /health
  - Mock VehicleManager

---

## File Structure

```
src/vehicles/
├── __init__.py
├── mavlink_client.py    # Single vehicle pymavlink wrapper
├── vehicle_manager.py   # Multi-vehicle orchestration
├── cot_generator.py     # VehicleStatus → CoT XML
├── cot_sender.py        # TCP sender to FreeTAKServer :8087
├── server.py            # FastAPI on :8003
└── tasks/
    └── todo.md          # This file
tests/test_vehicles/
├── __init__.py
├── test_cot_generator.py
├── test_vehicle_manager.py
└── test_server.py
```

## Build Order

Phase 1 → 2 → 3 → 4 → 5 (bottom-up, each phase testable independently)

## Integration Points

| Service | Direction | Endpoint |
|---|---|---|
| Coordinator :8000 | → us | `POST /execute` with MilitaryCommand |
| Dashboard via WS :8005 | ← us | `WebSocket /ws/telemetry` at 1 Hz |
| IFF Engine :8004 | → us | `POST /reclassify` |
| FreeTAKServer :8087 | ← us | CoT XML over TCP at 1 Hz |
| SITL :5760-5810 | ↔ us | MAVLink commands + telemetry |
