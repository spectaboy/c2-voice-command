# Agentic Loop Analysis: Why Complex Commands Fail

**Author:** Senior Systems Analysis
**Date:** 2026-03-20
**Status:** Root causes identified, fix plan proposed

---

## Table of Contents

1. [Complete Execution Flow Trace](#1-complete-execution-flow-trace)
2. [Root Cause Analysis — 6 Bugs](#2-root-cause-analysis--6-bugs)
3. [Alternative A: Agentic Loop Deep Dive](#3-alternative-a-agentic-loop-deep-dive)
4. [Honest Comparison: Current vs. Agentic Loop](#4-honest-comparison-current-vs-agentic-loop)
5. [Recommendation & Phased Plan](#5-recommendation--phased-plan)
6. [Code Examples](#6-code-examples)

---

## 1. Complete Execution Flow Trace

Every voice command flows through exactly 6 services in sequence. Here is the complete path from microphone to Gazebo motor command:

```
Operator Voice
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 1: Voice Server (src/voice/server.py)                       │
│ Port 8003 — FastAPI + WebSocket                                  │
│                                                                  │
│ WebSocket /ws/voice receives raw 16kHz PCM audio chunks          │
│ PTT mode: buffers chunks (line 208), on ptt_stop concatenates    │
│ and calls transcriber.transcribe() (line 193)                    │
│ Result: {"transcript": "...", "confidence": 0.95}                │
│ Fires asyncio.create_task(_emit_transcript(result)) (line 196)   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP POST to NLU /parse
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 2: NLU Service (src/nlu/server.py)                          │
│ Port 8002 — FastAPI                                              │
│                                                                  │
│ /parse endpoint (line 42) receives {"transcript": "..."}         │
│ Calls parser.parse(transcript) (line 47)                         │
│ Returns list[MilitaryCommand] as JSON                            │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 2a: NLU Parser (src/nlu/parser.py)                          │
│                                                                  │
│ Builds system prompt with fleet info, waypoints, entities        │
│ (lines 279-285)                                                  │
│                                                                  │
│ *** SINGLE Claude API call *** (lines 289-296)                   │
│   model: claude-haiku-4-5 (line 274)                             │
│   tool_choice: {"type": "any"} — forces tool use                 │
│   tools: 10 tool definitions from src/nlu/tools.py               │
│   messages: [{"role": "user", "content": transcript}]            │
│                                                                  │
│ Iterates response.content blocks (line 299-303)                  │
│ Each tool_use block → _tool_result_to_command() (line 301)       │
│ Returns list[MilitaryCommand]                                    │
│                                                                  │
│ KEY: This is a single-shot call. No multi-turn. No tool results  │
│ sent back. No state queries. Claude gets ONE chance to parse.     │
└──────────────────────────┬───────────────────────────────────────┘
                           │ Back in voice/server.py _emit_transcript()
                           │ Loop: for cmd in commands (line 304)
                           │ HTTP POST each to coordinator /command
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 3: Coordinator (src/coordinator/server.py)                  │
│ Port 8000 — FastAPI                                              │
│                                                                  │
│ /command endpoint (line 76) receives MilitaryCommand JSON        │
│ Step 1: assess_risk(command) (line 85) — sets risk_level         │
│ Step 2: IFF gate for ENGAGE (lines 88-127)                       │
│   - Queries IFF engine for target affiliation                    │
│   - FRIENDLY → blocked (line 97-106)                             │
│   - HOSTILE/UNKNOWN → confirmation_required                      │
│ Step 3: If requires_confirmation → hold + TTS readback           │
│ Step 4: If safe → route_command(command) (line 150)              │
│ Returns {"status": "executed"} immediately (lines 151-157)       │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP POST to vehicle bridge /execute
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 4: Router (src/coordinator/router.py)                       │
│                                                                  │
│ route_command() (line 29) dispatches by CommandType:             │
│   VEHICLE_COMMANDS set (line 18-26) → vehicle bridge             │
│   CLASSIFY → IFF engine                                          │
│   STATUS → vehicle bridge /telemetry                             │
│   ENGAGE → vehicle bridge (line 46-48)                           │
│                                                                  │
│ _send_to_vehicle_bridge() POSTs to localhost:8001/execute        │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 5: Vehicle Bridge (src/vehicles/server.py)                  │
│ Port 8001 — FastAPI                                              │
│                                                                  │
│ /execute endpoint (line 93-97)                                   │
│ Calls vehicle_manager.execute_command(cmd) (line 97)             │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 6: Vehicle Manager (src/vehicles/vehicle_manager.py)        │
│                                                                  │
│ execute_command() (line 91) → _execute_single() (line 107)      │
│ match cmd.command_type: (line 110)                               │
│   MOVE     → client.move_to(lat, lon, alt)          (line 111)  │
│   RTB      → client.rtb()                           (line 119)  │
│   LOITER   → client.set_mode("LOITER")              (line 123)  │
│   OVERWATCH→ client.move_to(lat, lon, alt)           (line 127) │
│   PATROL   → client.move_to(first location)          (line 140) │
│   TAKEOFF  → client.takeoff(alt)                     (line 148) │
│   LAND     → client.land()                           (line 153) │
│   _        → "Unsupported command type"              (line 157) │
│                                                                  │
│ Returns {"success": true/false} immediately                      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 7: MAVLink Client (src/vehicles/mavlink_client.py)          │
│                                                                  │
│ move_to() (line 186): sets GUIDED mode, sends                    │
│   set_position_target_global_int_send (line 203)                │
│   Fire-and-forget — returns True immediately                     │
│   Does NOT wait for waypoint reached                             │
│                                                                  │
│ takeoff() (line 162): GUIDED → arm → MAV_CMD_NAV_TAKEOFF        │
│ land() (line 219): sets LAND mode                                │
│ rtb() (line 226): sets RTL mode                                  │
│ set_mode() (line 133): sends mode change command                 │
│                                                                  │
│ All methods return immediately after sending the MAVLink packet  │
└──────────────────────────────────────────────────────────────────┘
```

**Key observation:** The entire pipeline is request-response. Every layer sends a command and immediately returns success. No layer waits for physical completion. No layer queries state before acting.

---

## 2. Root Cause Analysis — 6 Bugs

### Bug 1: ENGAGE Has No Handler in Vehicle Manager

**File:** `src/vehicles/vehicle_manager.py`, line 157
**Severity:** CRITICAL — ENGAGE commands silently fail

The `match cmd.command_type` block (lines 110-158) has cases for MOVE, RTB, LOITER, OVERWATCH, STATUS, PATROL, TAKEOFF, and LAND. There is **no** `case CommandType.ENGAGE:` handler.

When an ENGAGE command reaches `_execute_single()`, it falls through to:
```python
# Line 157-158
case _:
    return {"success": False, "error": f"Unsupported command type: {cmd.command_type}"}
```

**What happens in practice:**
1. Operator says "Alpha, engage hostile-01"
2. NLU correctly parses → `engage_target(callsign="UAV-1", target_uid="HOSTILE-01")`
3. Coordinator does IFF check, gets confirmation, routes to vehicle bridge
4. Vehicle bridge calls `vehicle_manager.execute_command()`
5. Falls to `case _:` → returns `{"success": False, "error": "Unsupported command type: engage"}`
6. The drone does absolutely nothing

**What it should do:** Navigate to the target's last-known position and orbit/track it. This requires looking up the target's position from the IFF/entity system and calling `client.move_to()` followed by `client.set_mode("LOITER")` or `client.set_mode("CIRCLE")`.

---

### Bug 2: PATROL Drops All Waypoints

**File:** `src/nlu/parser.py`, lines 218-227 and `src/vehicles/vehicle_manager.py`, lines 140-146
**Severity:** HIGH — patrol commands move to nothing

The `patrol_route` tool definition (`src/nlu/tools.py`, lines 96-125) takes a **`waypoints` array**, not top-level `lat`/`lon`:

```python
# tools.py line 109-120
"waypoints": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "alt_m": {"type": "number"},
        },
    },
}
```

But `_tool_result_to_command()` (parser.py lines 218-227) builds `Location` from **top-level** `tool_input.get("lat")` and `tool_input.get("lon")`:

```python
# parser.py lines 219-227
lat = tool_input.get("lat")    # None — patrol_route has no top-level lat
lon = tool_input.get("lon")    # None — patrol_route has no top-level lon
if lat is not None and lon is not None:
    location = Location(...)    # Never executes for patrol
```

The waypoints array ends up in `parameters` (line 232-233) but the vehicle manager never reads it:

```python
# vehicle_manager.py lines 140-146
case CommandType.PATROL:
    if cmd.location:          # cmd.location is None!
        await client.move_to(...)
    return {"success": True, "action": "patrol"}  # Returns success having done NOTHING
```

**What happens:** "Patrol between the bridge and the dockyard" → NLU correctly generates waypoints → all waypoints are silently dropped → drone doesn't move → dashboard says "patrol executed."

---

### Bug 3: LOITER Doesn't Navigate to Location

**File:** `src/vehicles/vehicle_manager.py`, lines 123-125
**Severity:** HIGH — loiter ignores the target position

The LOITER handler:
```python
# vehicle_manager.py lines 123-125
case CommandType.LOITER:
    await client.set_mode("LOITER")
    return {"success": True, "action": "loiter", "callsign": client.callsign}
```

It only changes the flight mode to LOITER. It **never navigates to the specified location**. Compare with the OVERWATCH handler (lines 127-134) which correctly calls `client.move_to()` first.

The `loiter_at` tool (`tools.py`, lines 127-159) accepts `lat`, `lon`, and `alt_m`. The NLU correctly parses these into a `Location` object. But the vehicle manager throws away the location entirely.

**What happens:** "Alpha, loiter at the bridge" → NLU parses location correctly → vehicle manager ignores location → drone stays where it is and switches to LOITER mode → dashboard says "holding position."

**What it should do:** `move_to(lat, lon, alt)` THEN `set_mode("LOITER")`.

---

### Bug 4: Dashboard Shows False "Executed" Status

**File:** `src/voice/server.py`, lines 332-336
**Severity:** MEDIUM — misleads the operator

When the coordinator returns `{"status": "executed"}`, the voice server immediately:
1. Generates a TTS readback like "UAV-1 proceeding to target location" (line 333-334)
2. Broadcasts `command_result` with status `"executed"` to the dashboard (line 336)

```python
# voice/server.py lines 332-336
elif coord_data.get("status") in ("executed", "confirmed_and_executed"):
    readback = _generate_execution_readback(cmd)
    if readback:
        asyncio.create_task(speak_with_effects(readback))
    await _broadcast_command_event("executed", cmd, readback or "Executed.")
```

But the coordinator returns "executed" the instant it sends the MAVLink command — before the drone begins moving. The MAVLink client (`mavlink_client.py`) is entirely fire-and-forget:

```python
# mavlink_client.py line 202-216 (move_to)
await asyncio.to_thread(
    self.conn.mav.set_position_target_global_int_send, ...
)
# Returns True immediately — no ACK wait, no waypoint-reached check
return True
```

**What happens:** Operator says "move to the bridge" → drone gets the MAVLink command → dashboard immediately shows "executed" → drone hasn't even started turning yet. For failed commands (e.g., Bug 1, 2, 3 above), the dashboard may still show executed because the success check happens at the coordinator level, not the physical level.

---

### Bug 5: No State Awareness in NLU

**File:** `src/nlu/parser.py`, lines 121-157 (SYSTEM_PROMPT)
**Severity:** MEDIUM — Claude parses blind

The system prompt injected into the Claude API call includes:
- Fleet info (callsigns, types, domains) — line 128
- Callsign aliases — line 131
- Waypoints — line 134
- IFF entity list — line 137

It does **NOT** include:
- Current vehicle positions (lat/lon/alt)
- Armed/disarmed state
- Current flight mode
- Battery levels
- Whether a vehicle is already airborne
- Whether a vehicle is currently executing another command

The NLU context module (`src/nlu/context.py`) provides command history (line 81-87) but zero live telemetry.

**Consequences:**
- "Move north" → Claude can't resolve this because it doesn't know current position
- "Land Alpha" when Alpha is already on the ground → sends redundant LAND command
- "Take off" when already at 100m → sends redundant TAKEOFF, may cause altitude reset
- Claude can't generate intelligent compound commands because it can't reason about current state

---

### Bug 6: No Compound Command Sequencing

**File:** `src/voice/server.py`, lines 304-339
**Severity:** MEDIUM — race conditions on multi-step commands

When the NLU returns multiple commands (e.g., "take off and fly to the bridge" → `[takeoff, move]`), the voice server fires them all to the coordinator in a tight loop with no delay:

```python
# voice/server.py line 304
for cmd in commands:
    # ... immediately POSTs each to coordinator
    coord_resp = await client.post("http://localhost:8000/command", json=cmd)
```

Each command is sent as soon as the HTTP response from the previous one returns — which is milliseconds. The coordinator processes each independently. There is no concept of "wait for takeoff to finish before sending move."

**Partial mitigation:** The MAVLink client's `move_to()` method (mavlink_client.py lines 193-196) has a check:
```python
if self.is_copter and (not self._armed or self._alt_m < 1.0):
    await self.takeoff(alt if alt > 0 else 10.0)
    await asyncio.sleep(2.0)
```
This auto-takeoff catches the common case but relies on a hardcoded 2-second delay and stale telemetry. It doesn't generalize to other sequences like "patrol then loiter" or "move to A then move to B."

**What breaks:** Complex commands like "fly to waypoint Alpha, then orbit for 5 minutes, then RTB" → all three fire simultaneously → only the last MAVLink command wins.

---

## 3. Alternative A: Agentic Loop Deep Dive

### What Is an Agentic Loop?

An **agentic loop** (also called multi-turn tool use) replaces the current single-shot Claude API call with an iterative conversation where Claude can:

1. **Call tools** to query system state (telemetry, IFF, weather)
2. **Receive tool results** back as messages
3. **Reason** about the results
4. **Call more tools** or **issue commands** based on what it learned
5. **Loop** until it decides the task is complete

Current architecture (single-shot):
```
Transcript → Claude (one call) → [tool_use blocks] → done
```

Agentic loop architecture:
```
Transcript → Claude → tool_use: get_vehicle_status("UAV-1")
         ← tool_result: {lat: 44.65, lon: -63.57, alt: 0, armed: false}
         → Claude → tool_use: takeoff_vehicle("UAV-1", 20)
         ← tool_result: {success: true}
         → Claude → tool_use: move_vehicle("UAV-1", 44.66, -63.58, 100)
         ← tool_result: {success: true}
         → Claude → [end_turn — no more tool calls]
```

### What It Would Fix

| Bug | Fixed by Agentic Loop? | How |
|-----|----------------------|-----|
| Bug 1: ENGAGE no handler | Partially — Claude could call `move_vehicle` to target position + `set_mode("CIRCLE")` instead of relying on a broken engage handler | Still need the handler for proper orbit behavior |
| Bug 2: PATROL waypoints dropped | YES — Claude would call `move_vehicle` for each waypoint sequentially, waiting for arrival confirmation | No more data-loss in the conversion layer |
| Bug 3: LOITER no navigation | YES — Claude would call `move_vehicle(lat, lon, alt)` then `set_loiter()` | Two-step sequence, natural for an agent |
| Bug 4: False "executed" | YES — Claude can poll `get_vehicle_status` to verify the drone actually arrived | Agent decides when the task is truly done |
| Bug 5: No state awareness | YES — Claude calls `get_vehicle_status` before planning | Agent sees live telemetry |
| Bug 6: No sequencing | YES — agent controls execution order, can wait between steps | This is the core value proposition |

### New Tools Needed for Agentic Approach

The current tool set (`src/nlu/tools.py`) is designed for Claude-as-parser (describe intent). An agentic loop needs tools that **execute actions and return results**:

```
QUERY TOOLS (new):
├── get_vehicle_status(callsign) → telemetry dict
├── get_all_vehicles() → list of telemetry
├── get_entity_info(uid) → IFF classification, position
├── get_waypoint(name) → {lat, lon, alt, description}
└── get_distance(from_callsign, to_lat, to_lon) → meters

ACTION TOOLS (modified from existing):
├── takeoff_vehicle(callsign, alt_m) → {success, error?}
├── move_vehicle(callsign, lat, lon, alt_m) → {success, error?}
├── set_loiter(callsign, lat?, lon?, alt_m?, duration_min?) → {success}
├── set_patrol(callsign, waypoints[]) → {success}
├── land_vehicle(callsign) → {success}
├── return_to_base(callsign) → {success}
├── set_mode(callsign, mode) → {success}
└── engage_target(callsign, target_uid) → {success, requires_confirmation?}

CONFIRMATION TOOLS:
└── request_operator_confirmation(message) → {confirmed: bool}
```

### Latency and Cost Analysis

**Current single-shot approach:**
- 1 API call to Claude Haiku
- ~300-500ms latency
- ~$0.0003 per command (Haiku pricing: $0.25/1M input, $1.25/1M output)
- Total: ~400ms, ~$0.0003

**Agentic loop approach:**
- 3-8 API calls per command (query state → plan → execute → verify)
- ~300-500ms per call = 900ms-4s total latency
- ~$0.001-0.004 per command with Haiku
- Could use Sonnet for complex planning: ~$0.005-0.02 per command

**Latency breakdown for "patrol between Alpha and Bravo":**

| Step | Action | Latency |
|------|--------|---------|
| 1 | `get_vehicle_status("UAV-1")` | ~400ms |
| 2 | `get_waypoint("Alpha")` + `get_waypoint("Bravo")` | ~400ms |
| 3 | Claude plans: need takeoff → move to Alpha → move to Bravo → loop | ~400ms |
| 4 | `takeoff_vehicle("UAV-1", 100)` | ~400ms |
| 5 | Poll until airborne (2-3 status checks) | ~1200ms |
| 6 | `move_vehicle("UAV-1", alpha_lat, alpha_lon, 100)` | ~400ms |
| **Total planning phase** | | **~3.2s** |

For voice C2, 3-4 seconds from "patrol between Alpha and Bravo" to seeing the drone start moving is acceptable. The current system takes ~400ms but the drone *doesn't actually patrol*.

**Cost at scale:**
- 100 commands/day × $0.003 avg = $0.30/day
- Negligible compared to Gazebo compute, SITL instances, etc.

---

## 4. Honest Comparison: Current vs. Agentic Loop

| Dimension | Current (Single-Shot) | Agentic Loop | Winner |
|-----------|----------------------|--------------|--------|
| **Latency** | ~400ms | ~2-4s | Current |
| **Simple commands** (takeoff, land, RTB) | Works correctly | Same result, slower | Current |
| **Complex commands** (patrol, loiter at X) | Broken (Bugs 2, 3) | Works correctly | Agentic |
| **Compound commands** ("take off and fly to X") | Race condition (Bug 6) | Sequenced properly | Agentic |
| **State awareness** | None (Bug 5) | Full telemetry access | Agentic |
| **Execution verification** | Fire-and-forget (Bug 4) | Can poll until done | Agentic |
| **Cost per command** | ~$0.0003 | ~$0.003 (10x) | Current |
| **Implementation complexity** | Simple, already built | Significant refactor | Current |
| **Debugging** | Single API call to inspect | Multi-turn trace to follow | Current |
| **Reliability** | Deterministic (same parse = same result) | Non-deterministic (LLM reasoning varies) | Current |
| **Extensibility** | Add tool definition + handler | Same, but agent can compose tools creatively | Agentic |
| **Safety/predictability** | Constrained to declared tools | Agent might combine tools unexpectedly | Current |

**Bottom line:** The agentic loop is strictly better for complex commands but adds latency and complexity for simple ones. The right answer is **not** "replace everything with an agentic loop" — it's "fix the bugs first, then add agentic capabilities for commands that need them."

---

## 5. Recommendation & Phased Plan

### Phase 1: Fix the Bugs (30 min) — Immediate Impact

These are pure code fixes. No architecture changes. Fix them first regardless of whether you adopt the agentic loop.

1. **Add ENGAGE handler** to `vehicle_manager.py` (line 157)
   - Look up target position from parameters
   - `move_to(target_lat, target_lon, alt)` → `set_mode("CIRCLE")`

2. **Fix PATROL waypoint extraction** in `parser.py` `_tool_result_to_command()`
   - Extract first waypoint from `waypoints` array for `cmd.location`
   - Store full waypoints array in `cmd.parameters`
   - Update `vehicle_manager.py` PATROL handler to use waypoints

3. **Fix LOITER navigation** in `vehicle_manager.py` (line 123)
   - Add `move_to()` call before `set_mode("LOITER")`

### Phase 2: Quick Wins (45 min) — High Value, Low Risk

4. **Add telemetry to NLU system prompt** in `parser.py`
   - Query vehicle bridge `/telemetry` endpoint
   - Inject current positions, modes, armed state into system prompt
   - Claude can now reason about "move north" and avoid redundant commands

5. **Add sequential command execution** in `voice/server.py`
   - Wait for coordinator response before sending next command
   - Add basic delay between commands (or check telemetry for completion)

6. **Honest execution status** in `voice/server.py`
   - Change "executed" to "command sent" in dashboard broadcast
   - Add a polling mechanism to check actual completion

### Phase 3: Agentic Loop (2-3 hrs) — Full Capability

7. **Implement the agentic loop** in `parser.py`
   - Replace single `client.messages.create()` with a loop
   - Add query tools (get_vehicle_status, get_waypoint, etc.)
   - Send tool results back to Claude and let it continue
   - Add a max-iterations guard (e.g., 15 turns)

8. **Add execution tools** that return real results
   - Tools call the coordinator/vehicle bridge and return actual success/failure
   - Claude can retry or adjust based on results

9. **Add safety rails**
   - Max iterations per command
   - Tool call rate limiting
   - Operator override ("cancel current operation")
   - Audit log of all agent decisions

---

## 6. Code Examples

### Fix 1: Add ENGAGE Handler (vehicle_manager.py)

```python
# In _execute_single(), add before the default case (line 155):

case CommandType.ENGAGE:
    # Move toward target position and orbit
    target_uid = cmd.parameters.get("target_uid", "")
    if cmd.location:
        # If NLU resolved a target position, fly there
        alt = cmd.location.alt_m if cmd.location.alt_m > 0 else 50.0
        await client.move_to(cmd.location.lat, cmd.location.lon, alt)
    # Set CIRCLE mode to orbit the target area
    await client.set_mode("CIRCLE")
    return {
        "success": True,
        "action": "engage",
        "callsign": client.callsign,
        "target_uid": target_uid,
    }
```

### Fix 2: Fix PATROL Waypoint Extraction (parser.py)

```python
# In _tool_result_to_command(), after the location-building block (after line 229),
# add special handling for patrol waypoints:

# Handle patrol_route waypoints — extract first waypoint as primary location
if tool_name == "patrol_route" and location is None:
    waypoints = tool_input.get("waypoints", [])
    if waypoints:
        first = waypoints[0]
        location = Location(
            lat=first["lat"],
            lon=first["lon"],
            alt_m=first.get("alt_m", 100.0 if domain == Domain.AIR else 0.0),
        )
```

And update the PATROL handler in `vehicle_manager.py`:

```python
case CommandType.PATROL:
    waypoints = cmd.parameters.get("waypoints", [])
    if waypoints:
        # Fly to first waypoint (full patrol requires AUTO mode + mission upload)
        first = waypoints[0]
        alt = first.get("alt_m", 100.0 if client.is_copter else 0.0)
        await client.move_to(first["lat"], first["lon"], alt)
    elif cmd.location:
        await client.move_to(
            cmd.location.lat, cmd.location.lon, cmd.location.alt_m
        )
    return {"success": True, "action": "patrol", "callsign": client.callsign}
```

### Fix 3: Fix LOITER Navigation (vehicle_manager.py)

```python
# Replace lines 123-125:
case CommandType.LOITER:
    if cmd.location:
        alt = cmd.location.alt_m if cmd.location.alt_m > 0 else 50.0
        await client.move_to(
            cmd.location.lat, cmd.location.lon, alt
        )
    await client.set_mode("LOITER")
    return {"success": True, "action": "loiter", "callsign": client.callsign}
```

### Fix 4: Add Telemetry to NLU System Prompt (parser.py)

```python
# Add to parser.py — new function:
async def _build_telemetry_info() -> str:
    """Fetch live telemetry and format for the system prompt."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://localhost:8001/telemetry")
            if resp.status_code != 200:
                return ""
            vehicles = resp.json()
    except Exception:
        return ""

    lines = ["## Live Vehicle Telemetry"]
    for v in vehicles:
        lines.append(
            f"- {v['callsign']}: pos=({v['lat']:.6f}, {v['lon']:.6f}, {v['alt_m']:.1f}m) "
            f"mode={v['mode']} armed={v['armed']} speed={v['speed_mps']:.1f}m/s "
            f"battery={v['battery_pct']:.0f}%"
        )
    return "\n".join(lines)

# Add {telemetry_info} to SYSTEM_PROMPT and populate in parse()
```

### Fix 5: Sequential Command Execution (voice/server.py)

```python
# Replace the tight loop in _emit_transcript() (line 304) with:
for i, cmd in enumerate(commands):
    logger.info("Forwarding command %d/%d to coordinator: %s %s",
                i + 1, len(commands),
                cmd.get("command_type"), cmd.get("vehicle_callsign"))
    try:
        coord_resp = await client.post(
            "http://localhost:8000/command", json=cmd
        )
        coord_data = coord_resp.json()
        # ... existing status handling ...

        # Wait between compound commands to allow execution
        if i < len(commands) - 1:
            await asyncio.sleep(2.0)

    except Exception as e:
        logger.warning("Failed to reach coordinator: %s", e)
```

### Phase 3: Agentic Loop Implementation (parser.py)

```python
# New method in NLUParser class:
QUERY_TOOLS = [
    {
        "name": "get_vehicle_status",
        "description": "Get current telemetry for a vehicle: position, altitude, mode, armed state, battery.",
        "input_schema": {
            "type": "object",
            "properties": {
                "callsign": {"type": "string", "description": "Vehicle callsign (e.g., 'UAV-1')"},
            },
            "required": ["callsign"],
        },
    },
    {
        "name": "get_waypoint",
        "description": "Look up a named waypoint's coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Waypoint name (e.g., 'Alpha', 'Bridge')"},
            },
            "required": ["name"],
        },
    },
    # ... more query tools ...
]

async def parse_agentic(self, transcript: str) -> list[MilitaryCommand]:
    """Parse with an agentic loop — multi-turn tool use."""
    system = self._build_system_prompt()  # same as before
    all_tools = TOOLS + QUERY_TOOLS
    messages = [{"role": "user", "content": transcript}]
    commands = []

    for turn in range(15):  # Safety: max 15 turns
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            tools=all_tools,
            messages=messages,
        )

        # Collect tool calls and results
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name in TOOL_TO_COMMAND_TYPE:
                    # This is an ACTION tool — convert to command
                    cmd = _tool_result_to_command(block.name, block.input, transcript)
                    commands.append(cmd)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"success": True, "queued": True}),
                    })
                else:
                    # This is a QUERY tool — execute and return result
                    result = await self._execute_query_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

        # If no tool calls, Claude is done
        if not tool_results:
            break

        # Add assistant response and tool results to conversation
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return commands

async def _execute_query_tool(self, tool_name: str, tool_input: dict) -> dict:
    """Execute a query tool and return the result."""
    import httpx

    if tool_name == "get_vehicle_status":
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://localhost:8001/telemetry")
            vehicles = resp.json()
            callsign = tool_input["callsign"]
            for v in vehicles:
                if v["callsign"] == callsign:
                    return v
            return {"error": f"Vehicle {callsign} not found"}

    elif tool_name == "get_waypoint":
        from src.shared.battlespace import get_waypoints
        name = tool_input["name"]
        waypoints = get_waypoints()
        for wp in waypoints:
            if wp["name"].lower() == name.lower():
                return wp
        return {"error": f"Waypoint {name} not found"}

    return {"error": f"Unknown query tool: {tool_name}"}
```

---

## Summary

The system works for simple, single-step commands (takeoff, land, RTB) because these map 1:1 from voice → tool call → MAVLink command. It fails on complex commands because:

1. **Data loss in translation:** Waypoints arrays, target positions, and loiter locations are parsed correctly by the NLU but dropped or ignored by downstream handlers.
2. **Missing handlers:** ENGAGE has no implementation at the vehicle level.
3. **No execution verification:** Every layer returns "success" before anything physically happens.
4. **No state context:** The NLU parses blind — it doesn't know where vehicles are or what they're doing.
5. **No sequencing:** Compound commands race against each other.

**Fixing bugs 1-3 takes 30 minutes and makes patrol, loiter, and engage work.** This is the highest-value work. The agentic loop (Phase 3) is the right long-term architecture for handling commands like "scout the harbor, report contacts, then RTB" — but it's not needed to make the current command set work. Fix the bugs first.
