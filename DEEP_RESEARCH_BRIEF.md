# Deep Research Brief — C2 Voice Command System

## What This Document Is

This is a comprehensive context document for Claude Code to do deep research and fix/rebuild the voice-driven C2 system for the CalgaryHacks hackathon on March 21, 2026 at SAIT, Calgary. Read every word — this is the ground truth of where we are, what's broken, and what we need.

---

## The Hackathon (March 21, 2026)

### What They Give Us
- **Cloud GPU VM** per team with Gazebo + ArduPilot SITL, browser access via noVNC
- **2 drones**: "Alpha" and "Bravo" on separate SITL ports (ArduPilot copters)
- **Waypoints**: Alpha through Hotel — GPS coordinates in a JSON file
- **Entity List**: JSON file with contacts classified FRIENDLY / UNKNOWN / HOSTILE
- **Practice dataset**: Test commands to validate our system
- **Hacking Time**: 9:50 AM - 4:00 PM (~6 hours), then demos

### What They Evaluate
1. **Basic drone commands** — takeoff, navigation to waypoints, landing
2. **Compound and parameterized commands** — "take off to 30 meters then fly to Bravo"
3. **IFF safety enforcement** — block friendly engagement, confirm unknowns, confirm hostiles
4. **Multi-drone coordination** — both drones moving at once
5. **Graceful handling of ambiguous, contradictory, or invalid input**
6. **Live demo** — 5-minute presentation showing voice integration, UX polish, creative features

### The Scenario
You are an operator at a forward operating base. You have 2 drones on the pad. The battlespace has waypoints (Alpha-Hotel) and known contacts (friendly, hostile, unknown). You speak commands and the drones respond in a 3D Gazebo simulation visible in your browser.

**The core question: can your system turn voice into controlled, safe action?**

---

## Current Architecture

```
Voice (mic) → Whisper STT → Claude NLU (tool-calling) → Coordinator (risk/IFF) → Vehicle Bridge (pymavlink) → ArduPilot SITL
                                                                                         ↓
Dashboard (React) ← WebSocket Hub ← telemetry + events                              Gazebo 3D
```

### Services (all running locally)
| Service | Port | Tech |
|---------|------|------|
| Voice ASR | 8001 | faster-whisper (small model on CPU) |
| NLU Parser | 8002 | Claude Haiku 4.5 via Anthropic API, tool-calling |
| Coordinator | 8000 | FastAPI, risk assessment, confirmation flow |
| Vehicle Bridge | 8003 | pymavlink, VehicleManager |
| IFF Engine | 8004 | Contact tracker, rules engine, audit trail |
| WebSocket Hub | 8005 | Event aggregation, dashboard broadcast |
| Mock SITL | 5760-5770 | Pure Python mock ArduPilot (for dev without WSL) |
| Dashboard | 3000 | React + Leaflet tactical map |

### Data Files (in data/)
- `waypoints.json` — Alpha through Hotel + Halifax landmarks
- `entities.json` — 6 contacts (2 friendly, 2 hostile, 2 unknown)
- `fleet.json` — 2 drones: Alpha (port 5760) and Bravo (port 5770)

---

## CRITICAL ISSUES — NONE OF THESE ARE FULLY FIXED

### Issue 1: Drones Don't Visually Move in Real-Time on the Map

**What happens**: You give a command, the log says "executed", but the drone marker on the Leaflet map barely moves or appears to teleport. There is no smooth live tracking where you see the drone moving point by point along its path.

**Root causes**:
- The telemetry broadcast loop in `src/vehicles/server.py` sends position updates. It was at 1Hz, bumped to 4Hz (0.25s), but the dashboard may not be rendering intermediate positions smoothly.
- The mock SITL physics in `src/vehicles/mock_sitl.py` update at 10Hz internally, but the positions sent to the dashboard may jump too far between updates.
- The Leaflet map markers just snap to new positions — there is no animation/interpolation between position updates.
- The trail (polyline) only shows where the vehicle HAS BEEN, not smooth movement.

**What needs to happen**:
- Dashboard needs to interpolate/animate marker positions between WebSocket updates
- OR the telemetry rate needs to be high enough (4-10Hz) that discrete position jumps look smooth
- Vehicle markers should visibly glide across the map as the drone moves
- The trail should draw behind the moving marker in real-time

### Issue 2: NLU Doesn't Understand Intent or Context

**What happens**: When you say "move to the intersection of Barrington and Duke", the NLU resolves it to approximate coordinates. But it doesn't understand spatial reasoning — "go up a little", "move behind the hill", "stay on the road", "take a right at Duke Street". It also doesn't handle corrections well — "my bad, I meant UGV-1" just confuses it.

**Root causes**:
- The NLU system prompt is a flat list of rules. There's no contextual understanding.
- Claude has no awareness of the current positions of the drones or contacts.
- Claude has no map/spatial awareness — it can't reason about "behind", "north of", "near", etc.
- There is no conversation history — each transcript is parsed independently with no memory of what was just said.

**What needs to happen**:
- The NLU system prompt should include CURRENT vehicle positions so Claude can reason spatially ("move 500m north", "go to where Bravo is", "move closer to the hostile")
- The NLU should receive recent command history so it can handle corrections ("actually send it to Delta instead")
- The NLU context module (`src/nlu/context.py`) exists but may not be feeding enough context
- Consider adding current vehicle telemetry to the system prompt

### Issue 3: IFF/Engage/Classify Not Working End-to-End

**What happens**: When you say "engage the hostile vehicle", the system should:
1. Parse → `engage_target(callsign="Alpha", target_uid="hostile-vehicle-1")`
2. Coordinator → check IFF → hostile → CRITICAL risk → require confirmation
3. TTS speaks readback: "CONFIRM: CRITICAL RISK. Engaging hostile-vehicle-1."
4. Operator says "CONFIRM" → execute

But in practice:
- The NLU sometimes fails to map natural descriptions ("the hostile vehicle") to the correct `target_uid` from the entity list
- The IFF engine returned 422 because contacts didn't exist (partially fixed — auto-create added)
- The coordinator sends affiliation as full word ("hostile") but IFF expected single char ("h") (partially fixed — normalization added)
- There's no visual representation of contacts on the dashboard map — you can't see friendlies/hostiles/unknowns
- The confirmation flow via voice works in theory but hasn't been tested end-to-end

### Recent Merge: IFF/Engage Pipeline Rework (branch 9d8b2b8)

A parallel branch made significant improvements that have been merged. Understand these changes — they are the current ground truth for how IFF/engage works:

**1. IFF/Engage flow moved to coordinator handler.** Previously `assess_risk()` was async and made its own HTTP call to the IFF engine, stuffing hacky `_blocked`/`_block_reason` keys into the command parameters dict. Now `assess_risk()` is synchronous (pure risk classification only). The coordinator's `handle_command()` calls `lookup_iff(target_uid)` directly from `router.py`, gets the full IFF result (affiliation, threat_score, confidence, indicators), then decides: friendly → blocked, hostile/unknown → confirmation required. This is cleaner separation of concerns.

**2. Entity UID resolution added in NLU parser.** `_resolve_entity_uid()` in `parser.py` maps fuzzy operator-spoken names to exact IFF UIDs. It loads aliases from `data/entity_list.json` (note: different from `data/entities.json` — the alias loader looks for `entity_list.json`). Strips dashes, underscores, leading zeros for fuzzy matching. E.g. `"hostile vehicle"` → `"hostile-vehicle-1"`.

**3. `_notify_confirmation()` helper in coordinator.** Fires BOTH voice TTS readback (POST to voice `/readback`) AND WS hub broadcast (dashboard confirmation modal) in one call. Used for all confirmation flows.

**4. `generate_engage_readback()` in risk.py.** Generates detailed readback including threat score, confidence, and indicators from the IFF result. Falls back to "IFF status unavailable" warning if IFF engine is down.

**5. `lookup_iff()` in router.py.** Queries IFF engine `/contact/{uid}` endpoint. Returns full contact dict or None. Used by coordinator for ENGAGE gating.

**6. Pending confirmation queue in voice server.** `_pending_confirmations` changed from a single `dict["active"]` to a `list[str]` (FIFO queue). Supports `CONFIRM ALL` and `CANCEL ALL` for multi-command confirmation.

**Key file note:** The entity alias loader (`_load_entity_aliases()` in parser.py) looks for `data/entity_list.json`, NOT `data/entities.json`. These may need to be reconciled — either rename the file or update the loader path.

### Issue 4: No Gazebo / 3D Simulation

**What happens**: We only have a 2D Leaflet map. The hackathon provides Gazebo (3D robotics simulator) rendered via noVNC in the browser. Drones need to fly visibly in 3D.

**What we need**:
- Understand how ArduPilot SITL connects to Gazebo
- Our pymavlink commands should work unchanged against real SITL (same MAVLink protocol)
- We need to test with real ArduPilot SITL, not just our mock
- On hackathon day, we'll point our Vehicle Bridge at their SITL IP/ports instead of localhost
- Research: How to install ArduPilot SITL + Gazebo Harmonic in WSL2 for pre-testing
- Research: What ArduPilot parameters/modes we need for the demo (GUIDED mode, takeoff, waypoint navigation, RTL, LAND)

### Issue 5: System Only Handles 2 Drone Types

**What we changed**: Fleet config now has just Alpha and Bravo (both ArduCopter). We removed UGV/USV.

**What needs to happen**:
- The entire codebase should be optimized for 2 copter drones
- Remove ground/maritime vehicle code paths or make them no-ops
- Focus on being THE BEST at copter control: takeoff, precise waypoint navigation, altitude control, landing, RTL, loiter/orbit
- The NLU should deeply understand copter-specific commands

### Issue 6: No Contacts Shown on Dashboard Map

**What happens**: The IFF engine tracks contacts (friendlies, hostiles, unknowns) but they don't appear on the tactical map. You can only see your own drones.

**What needs to happen**:
- The dashboard should show entity markers on the map — green for friendly, red for hostile, yellow for unknown
- When IFF classification changes, markers should update color
- Clicking a contact should show its details
- The IFF audit trail panel should show classification changes

### Issue 7: TTS Readback Inconsistent

**What happens**: TTS (edge-tts) sometimes plays, sometimes doesn't. The readback for executed commands was added but isn't always audible.

**What needs to happen**:
- Every executed command should have voice confirmation: "Alpha taking off to 20 meters", "Bravo proceeding to waypoint Charlie"
- Blocked commands should speak: "BLOCKED: Cannot engage friendly forces"
- Confirmation requests should speak the readback clearly
- Ensure edge-tts + sounddevice actually works reliably on Windows

---

## Research Tasks Needed

### 1. ArduPilot SITL Deep Dive
- How does ArduPilot SITL work? What protocols? What ports?
- MAVLink message types we need: HEARTBEAT, GLOBAL_POSITION_INT, SET_POSITION_TARGET_GLOBAL_INT, COMMAND_LONG (takeoff, land, arm/disarm, set mode)
- ArduCopter flight modes: GUIDED, AUTO, RTL, LAND, LOITER — when to use each
- How to do precise waypoint navigation (fly to exact GPS coordinate)
- How to do altitude control (fly to specific altitude)
- How to orbit/loiter at a point
- How to handle arm checks and pre-arm failures
- MAVSDK-Python vs pymavlink — pros/cons for hackathon (they recommend MAVSDK)

### 2. Gazebo Integration
- How does ArduPilot SITL connect to Gazebo?
- The hackathon provides a cloud VM with Gazebo already running — what do we need to do?
- How to install Gazebo Harmonic + ArduPilot SITL in WSL2 for local testing
- What does the Gazebo visualization look like? noVNC setup?
- Do we need any Gazebo plugins or just ArduPilot SITL + Gazebo world file?
- Can we test locally with QGroundControl as an alternative visual?

### 3. Intent Extraction / NLU Research
- How do military C2 voice systems handle natural language commands?
- Research papers on voice-to-drone-command systems
- How to handle spatial reasoning ("move north", "go behind the hill", "fly over the bridge")
- How to handle relative commands ("move 500 meters east", "go higher", "come back a little")
- How to maintain conversation context for corrections ("actually, send Bravo instead")
- Best practices for tool-calling NLU with Claude — system prompt engineering
- How to inject real-time vehicle state into the NLU prompt for spatial awareness

### 4. Safety & IFF Logic
- How should IFF engagement rules work in military C2 systems?
- Best practices for confirmation flows (voice-based confirmation)
- How to visualize the IFF state on a tactical dashboard
- Research on Rules of Engagement (ROE) for autonomous systems

### 5. Hackathon Scenario Replication
- We need to build a complete test scenario that replicates what the hackathon will give us:
  - 2 drones on the pad (SITL instances)
  - Waypoints Alpha-Hotel (GPS coordinates)
  - Entity list with friendlies/hostiles/unknowns
  - Practice dataset of voice commands to test against
- Create a test script that runs through all expected commands and validates results
- Test edge cases: gibberish input, contradictory commands, ambiguous callsigns, wrong vehicle type for command

---

## Key Source Files

| File | What It Does | What's Wrong |
|------|-------------|-------------|
| `src/voice/config.py` | Whisper model config | Auto-selects small on CPU. Hackathon will have GPU — needs large-v3-turbo |
| `src/voice/transcriber.py` | Whisper wrapper | Works, but small model has lower accuracy for military vocab |
| `src/voice/server.py` | Voice WebSocket + pipeline orchestration | Broadcasts transcript immediately, then NLU+coordinator. TTS readback added but untested |
| `src/voice/tts.py` | Edge TTS with radio effects | Works in isolation, unreliable in pipeline |
| `src/nlu/parser.py` | Claude tool-calling NLU | tool_choice="any" forces tool calls. System prompt needs vehicle positions for spatial reasoning |
| `src/nlu/tools.py` | 10 Claude tools (move, takeoff, land, etc.) | Complete but may need refinement for 2-drone scenario |
| `src/nlu/context.py` | Command history + corrections | Exists but may not feed enough context to Claude |
| `src/coordinator/server.py` | Risk assessment + confirmation flow | Works for basic flow. Confirmation modal URL fixed. CORS added |
| `src/coordinator/risk.py` | IFF check on ENGAGE commands | Queries IFF engine, blocks friendlies, confirms unknowns/hostiles |
| `src/coordinator/router.py` | Routes commands to vehicle bridge or IFF | Affiliation normalization added (hostile→h) |
| `src/vehicles/vehicle_manager.py` | Manages MAVLink connections | Uses fleet config. Handles TAKEOFF, LAND, MOVE, RTB, etc. |
| `src/vehicles/mavlink_client.py` | Single pymavlink connection | Works against both mock SITL and real ArduPilot SITL |
| `src/vehicles/mock_sitl.py` | Pure Python mock ArduPilot | Speed increased. Uses fleet config. Physics at 10Hz |
| `src/vehicles/server.py` | Vehicle bridge FastAPI | Telemetry broadcast at 4Hz. httpx logging suppressed |
| `src/iff/server.py` | IFF classification engine | Auto-creates contacts. Pre-loads from entities.json |
| `src/shared/battlespace.py` | Loads waypoints/entities/fleet from data/ | Falls back to defaults. Builds NLU prompt sections |
| `src/shared/constants.py` | Ports, callsign aliases | Aliases updated for Alpha/Bravo fleet |
| `src/shared/schemas.py` | Pydantic models | CommandType includes TAKEOFF, LAND |
| `src/dashboard/src/App.tsx` | React dashboard root | Confirmation modal posts to coordinator:8000 |
| `src/dashboard/src/components/TacticalMap.tsx` | Leaflet map | Centered on Halifax. No contact markers yet |
| `src/dashboard/src/components/TranscriptLog.tsx` | Voice transcript log | Color-coded: green=executed, red=blocked/error, yellow=confirmation |
| `src/dashboard/src/components/StatusCards.tsx` | Vehicle status cards | Shows mode, speed, heading, altitude, battery |
| `src/dashboard/src/hooks/useAppState.ts` | State management | Handles command_result, command_error events |
| `data/waypoints.json` | Waypoints Alpha-Hotel + Halifax landmarks | |
| `data/entities.json` | 6 contacts (2 friendly, 2 hostile, 2 unknown) | |
| `data/fleet.json` | 2 drones: Alpha and Bravo | |

---

## What "Best of the Best" Looks Like for This Hackathon

1. **Sub-3-second voice-to-action** — Operator speaks, drone responds in under 3 seconds
2. **Precise waypoint navigation** — "Fly to Waypoint Bravo" → drone flies exactly there in Gazebo
3. **Smooth visual feedback** — See the drone moving in real-time on map AND in Gazebo
4. **Smart IFF enforcement** — "Engage the friendly patrol" → instantly blocked with voice warning
5. **Natural conversation** — "Go investigate that unknown contact" → drone flies to contact location
6. **Multi-drone coordination** — "Alpha and Bravo, fly to Charlie" → both move simultaneously
7. **Compound commands** — "Take off to 30 meters then fly to Delta" → takeoff + move in sequence
8. **Error handling** — Gibberish → "Could not understand, please repeat". Wrong vehicle → graceful fallback
9. **Voice confirmation flow** — High-risk action → TTS readback → voice confirm/cancel → execute/abort
10. **Polished dashboard** — Live telemetry, command log with parsed results, IFF audit trail, contact markers on map

---

## Priority for Next Session

1. **Get Gazebo + real ArduPilot SITL working** — This is the #1 blocker. Without it we're demoing on a 2D map.
2. **Fix live movement visualization** — Drones must visibly move on the map/Gazebo in real-time
3. **Add contacts to the tactical map** — Show friendlies/hostiles/unknowns as colored markers
4. **Test full IFF flow end-to-end** — Engage hostile → confirm → execute. Engage friendly → blocked.
5. **Add vehicle positions to NLU context** — So Claude can understand "go north", "move closer", relative commands
6. **Build test script** — Automated test of all expected voice commands
7. **Optimize for 2 copter drones** — Remove unnecessary vehicle type handling, focus on ArduCopter excellence
