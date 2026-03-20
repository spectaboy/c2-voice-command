# Voice-driven drone C2 system: complete hackathon blueprint

**Build a voice-controlled dual-drone command system in 6 hours by pre-assembling five modular components — STT, LLM parser, IFF safety engine, MAVSDK controller, and Streamlit dashboard — then wiring them to event-specific configs on the day.** The automated scoring rewards robust natural language understanding, strict IFF rule enforcement, and graceful edge-case handling far more than visual polish. This blueprint provides verified code patterns, critical gotchas, and a minute-by-minute execution plan for SAIT Calgary on March 21, 2026.

---

## The architecture that wins in 6 hours

The system uses a **two-process architecture**: a FastAPI async backend (handling MAVSDK drone control, command parsing, IFF validation, and WebSocket communication) and a Streamlit frontend (displaying telemetry, maps, command logs, and confirmation prompts). This separation exists because Streamlit re-runs its entire script on every interaction, which conflicts with MAVSDK's persistent async connections.

```
Browser (Streamlit + Web Speech API)
    │
    ├── Web Speech API ──text──► FastAPI Backend ──► Command Parser (Instructor + GPT-4o-mini)
    │                               │                       │
    ├── MediaRecorder ──audio──►    │               IFF Safety Engine
    │   (fallback)                  │                       │
    │                               ├──► MAVSDK System(port=50051) ──► Alpha SITL (UDP :14550)
    │                               └──► MAVSDK System(port=50052) ──► Bravo SITL (UDP :14560)
    │
    └── Polls FastAPI /status every 2s ──► Streamlit renders telemetry + map + command log
```

**Core dependencies** (pre-install everything):
```
pip install mavsdk fastapi uvicorn websockets instructor openai pydantic
pip install faster-whisper streamlit streamlit-folium streamlit-autorefresh folium
```

---

## MAVSDK-Python patterns that actually work with ArduPilot

MAVSDK-Python uses a client-server architecture where your Python code communicates via gRPC with an embedded C++ `mavsdk_server` binary. Each `System()` instance starts its own server process. For two drones, **each needs a unique gRPC port** — this is the single most important multi-drone detail.

### Connecting two drones simultaneously

```python
from mavsdk import System

async def connect_drone(name: str, udp_port: int, grpc_port: int) -> System:
    drone = System(port=grpc_port)  # UNIQUE per drone
    await drone.connect(system_address=f"udp://:{udp_port}")

    async for state in drone.core.connection_state():
        if state.is_connected:
            break

    # CRITICAL: Do NOT use health_all_ok() — always returns false on ArduPilot
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            break

    return drone

alpha = await connect_drone("Alpha", udp_port=14550, grpc_port=50051)
bravo = await connect_drone("Bravo", udp_port=14560, grpc_port=50052)
```

ArduPilot SITL port formula: instance N uses UDP ports **14550 + 10×N** and **14551 + 10×N**. Instance 0 (Alpha) gets 14550/14551; instance 1 (Bravo) gets 14560/14561.

### The goto_location AMSL altitude trap

This is the **#1 crash-causing bug** with MAVSDK + ArduPilot. The `goto_location()` method takes absolute altitude (Above Mean Sea Level), not height above ground. Passing `20` when your SITL home is at 584m AMSL sends the drone underground.

```python
async def fly_to(drone: System, lat: float, lon: float, alt_above_ground: float):
    # Fetch home AMSL altitude first
    async for home in drone.telemetry.home():
        home_amsl = home.absolute_altitude_m
        break

    target_amsl = home_amsl + alt_above_ground
    await drone.action.goto_location(lat, lon, target_amsl, 0)
```

**Cache `home_amsl` once at startup** — querying it every command wastes time.

### Complete operation patterns

```python
# Takeoff — arm() + takeoff() automatically enters GUIDED mode on ArduPilot
await drone.action.set_takeoff_altitude(altitude_m)
await drone.action.arm()
await drone.action.takeoff()  # Must follow arm() within ~15 seconds or auto-disarm

# Land
await drone.action.land()

# RTL — drone rises to RTL altitude, flies home, lands
await drone.action.return_to_launch()

# Set speed
await drone.action.set_current_speed(speed_m_s)

# Single telemetry reading
async for pos in drone.telemetry.position():
    return pos  # latitude_deg, longitude_deg, relative_altitude_m, absolute_altitude_m
```

### Seven ArduPilot-specific gotchas

| Issue | Impact | Fix |
|-------|--------|-----|
| `health_all_ok()` always false | Blocks forever | Check `is_global_position_ok` + `is_home_position_ok` individually |
| `goto_location` uses AMSL altitude | Drone crashes into ground | Add `home.absolute_altitude_m` to desired AGL |
| `do_orbit()` returns COMMAND_DENIED | Orbit doesn't work | Implement circular waypoints manually or skip |
| `hold()` is PX4-specific | May fail silently | Use `goto_location` to current position |
| Flight mode shows "HOLD" during goto | Confusing telemetry | Track movement via position changes instead |
| Arm auto-disarms after ~15s | Motors stop unexpectedly | Call `takeoff()` immediately after `arm()` |
| Multi-drone without unique gRPC ports | Second drone fails | Use `System(port=50051+i)` |

---

## Speech-to-text: Web Speech API primary, faster-whisper fallback

For a CPU-only laptop with **6 hours to build**, the Web Speech API running in the browser is the fastest path to working voice input. It sends audio to Google's servers (in Chrome) and returns text in **200–600ms** with ~95%+ accuracy — zero Python dependencies needed. The fallback for offline scenarios is faster-whisper with the `base.en` model using INT8 quantization, delivering **~0.5–1.2s** latency for short commands on CPU.

### Browser-side push-to-talk (complete implementation)

```javascript
const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
recognition.continuous = false;
recognition.interimResults = false;
recognition.lang = 'en-US';

document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !e.repeat) {
        recognition.start();
        document.getElementById('status').textContent = '🔴 Listening...';
    }
});

document.addEventListener('keyup', (e) => {
    if (e.code === 'Space') {
        recognition.stop();
        document.getElementById('status').textContent = '⚪ Ready';
    }
});

recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    // Send text directly to FastAPI backend — no audio processing needed
    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ command: transcript, source: 'webspeech' })
    });
};

recognition.onerror = (e) => {
    if (e.error === 'network') switchToLocalWhisper();  // Fallback trigger
};
```

### faster-whisper fallback (pre-load model at startup)

```python
from faster_whisper import WhisperModel

# Load once at startup — model stays in memory
model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4)

def transcribe(audio_path: str) -> str:
    segments, _ = model.transcribe(
        audio_path,
        beam_size=1,          # Faster than default 5
        language="en",         # Skip language detection
        vad_filter=True,       # Skip silence
        without_timestamps=True # Skip timestamp generation
    )
    return " ".join(s.text for s in segments).strip()
```

**Model selection guide**: `base.en` (74M params, ~388MB RAM, ~95% accuracy) is the sweet spot. Use `tiny.en` if you need sub-500ms. Never use medium or larger on CPU for real-time commands. Pre-download models at home — `WhisperModel("base.en")` caches to `~/.cache/huggingface/`.

| Approach | Latency | Accuracy | Internet | Build time |
|----------|---------|----------|----------|------------|
| **Web Speech API** | 200–600ms | ~95%+ | Required | 30 min |
| **faster-whisper base.en INT8** | 0.5–1.2s | ~95% | No | 1 hour |
| **Hybrid (recommended)** | 200ms–1.2s | ~95%+ | Preferred | 1.5 hours |

---

## Command parser: Instructor + GPT-4o-mini with Pydantic schemas

The `instructor` library (11k+ GitHub stars, 3M+ monthly downloads) wraps any LLM API to return validated Pydantic models. Combined with GPT-4o-mini (~200–500ms per call, ~$0.15/million input tokens), it handles the full spectrum of commands the scoring system will test — including compound, ambiguous, and contradictory inputs — in about **10 lines of core code**.

### Pydantic schema (discriminated union pattern)

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Union

class TakeoffCommand(BaseModel):
    command_type: Literal["takeoff"]
    target_drone: Optional[str] = None
    altitude_meters: Optional[float] = Field(None, ge=1, le=120)

class NavigateCommand(BaseModel):
    command_type: Literal["navigate"]
    target_drone: Optional[str] = None
    waypoint_name: Optional[str] = None
    altitude_meters: Optional[float] = Field(None, ge=1, le=120)
    speed_mps: Optional[float] = Field(None, ge=0.5, le=30)

class EngageCommand(BaseModel):
    command_type: Literal["engage"]
    target_drone: Optional[str] = None
    action: Literal["engage", "attack", "strike", "neutralize",
                     "intercept", "investigate", "track"]
    target_entity: str

class LandCommand(BaseModel):
    command_type: Literal["land"]
    target_drone: Optional[str] = None

class RTBCommand(BaseModel):
    command_type: Literal["return_to_base"]
    target_drone: Optional[str] = None

class QueryCommand(BaseModel):
    command_type: Literal["query"]
    target_drone: Optional[str] = None
    query_subject: Literal["altitude", "position", "speed", "status", "battery"]

class CompoundCommand(BaseModel):
    command_type: Literal["compound"]
    sub_commands: List[Union[TakeoffCommand, LandCommand, NavigateCommand,
                            EngageCommand, RTBCommand, QueryCommand]]

class AmbiguousCommand(BaseModel):
    command_type: Literal["ambiguous"]
    raw_input: str
    reason: str
    possible_interpretations: List[str] = []

class InvalidCommand(BaseModel):
    command_type: Literal["invalid"]
    raw_input: str
    reason: str
    error_type: Literal["contradictory", "impossible_parameters", "nonsense", "incomplete"]

class ParsedInput(BaseModel):
    commands: List[Union[TakeoffCommand, LandCommand, NavigateCommand,
                         EngageCommand, RTBCommand, QueryCommand,
                         CompoundCommand, AmbiguousCommand, InvalidCommand]]
    confidence: float = Field(ge=0, le=1)
    raw_input: str
```

### Parser with Instructor (the actual parsing code)

```python
import instructor

client = instructor.from_provider("openai/gpt-4o-mini")

SYSTEM_PROMPT = """You are a military drone command parser. Parse voice commands into structured drone commands.

RULES:
1. Identify target drone by callsign (Alpha, Bravo). None = default/all.
2. "Both drones" → separate commands for each drone.
3. Compound commands ("take off and fly to Charlie") → CompoundCommand.
4. Contradictory commands ("take off and land") → InvalidCommand.
5. Vague input ("go there", "do that") → AmbiguousCommand.
6. "fly to Alpha" when Alpha is both callsign AND waypoint → AmbiguousCommand.
7. Engagement verbs: engage, attack, strike, neutralize, intercept, investigate, track.

KNOWN DRONES: {callsigns}
KNOWN WAYPOINTS: {waypoints}"""

def parse_command(text: str, callsigns: list, waypoints: list) -> ParsedInput:
    return client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=ParsedInput,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(
                callsigns=callsigns, waypoints=waypoints)},
            {"role": "user", "content": text}
        ],
        max_retries=2,  # Auto-retries on Pydantic validation failure
    )
```

**Why this approach dominates for automated scoring**: GPT-4o-mini reliably handles every edge case — contradictions, ambiguity, name collisions, compound commands — that would require hundreds of regex rules to match. The `instructor` library guarantees the output matches your Pydantic schema, with built-in retry logic if the LLM produces invalid JSON. Latency of **200–500ms** is acceptable for command processing.

**Fallback strategy**: If GPT-4o-mini is unreachable, use regex patterns for the 5 most common commands (takeoff, land, goto waypoint, RTB, status query). This covers basic scoring while the API recovers.

---

## IFF safety engine: the interceptor that earns major points

The IFF engine sits between the parser and executor as a validation middleware. It loads the entity JSON at startup and applies three rules. **FRIENDLY targets are always blocked. UNKNOWN targets require confirmation. HOSTILE targets allow action but confirm high-risk engagement verbs (engage, attack, strike, neutralize).**

```python
ENGAGEMENT_VERBS = {"engage", "attack", "strike", "neutralize", "intercept", "investigate", "track"}
HIGH_RISK_VERBS = {"engage", "attack", "strike", "neutralize"}

class IFFSafetyEngine:
    def __init__(self, entities_path: str):
        with open(entities_path) as f:
            data = json.load(f)
        self.entities = {e["name"].lower(): e for e in data}

    def validate(self, command) -> tuple[str, str]:
        """Returns (action, message) where action is ALLOW/BLOCK/CONFIRM."""
        if isinstance(command, EngageCommand):
            entity = self.entities.get(command.target_entity.lower())
            if entity is None:
                return "CONFIRM", f"Entity '{command.target_entity}' not in database. Proceed?"
            iff = entity["classification"]
            if iff == "FRIENDLY":
                return "BLOCK", f"⚠️ BLOCKED: {command.target_entity} is FRIENDLY"
            if iff == "UNKNOWN":
                return "CONFIRM", f"Entity '{command.target_entity}' is UNKNOWN. Confirm {command.action}?"
            if iff == "HOSTILE" and command.action in HIGH_RISK_VERBS:
                return "CONFIRM", f"Confirm {command.action} on HOSTILE '{command.target_entity}'?"
            return "ALLOW", f"Approved: {command.action} on HOSTILE target"

        if isinstance(command, NavigateCommand) and command.waypoint_name:
            nearby = self._entities_near_waypoint(command.waypoint_name)
            friendlies = [e for e in nearby if e["classification"] == "FRIENDLY"]
            if friendlies:
                names = ", ".join(e["name"] for e in friendlies)
                return "CONFIRM", f"Friendly entities ({names}) near destination. Proceed?"

        return "ALLOW", "Command cleared"
```

**Confirmation flow for automated scoring**: When IFF returns `CONFIRM`, the system sends a prompt to the operator and waits for a verbal or typed response. Match affirmative words (`yes, confirm, affirmative, roger, proceed, execute`) and negative words (`no, deny, negative, cancel, abort`). Store pending confirmations with a **30-second timeout** that auto-denies. This likely maps to how the scoring system expects the confirmation loop to work — it sends a command, checks that the system requests confirmation, then sends an affirmative/negative follow-up.

**Edge case: "fly to Alpha"** where Alpha is both a drone callsign and a waypoint name. The LLM parser flags this as `AmbiguousCommand`. The system responds: "Did you mean fly to Waypoint Alpha, or are you addressing Drone Alpha?" This earns disambiguation points.

---

## Streamlit dashboard polling a FastAPI backend

The Streamlit frontend polls the FastAPI backend every **2 seconds** using `streamlit-autorefresh`. This gives a live-updating tactical display without fighting Streamlit's rerun model. All async logic (MAVSDK, WebSocket, command processing) lives in FastAPI.

### FastAPI backend core (simplified)

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

drones = {}  # {"alpha": DroneState, "bravo": DroneState}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect both drones at startup
    drones["alpha"] = await connect_drone("Alpha", 14550, 50051)
    drones["bravo"] = await connect_drone("Bravo", 14560, 50052)
    # Start telemetry background tasks
    for name in drones:
        asyncio.create_task(telemetry_loop(name))
        asyncio.create_task(command_worker(name))
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/api/command")
async def handle_command(payload: dict):
    text = payload["command"]
    parsed = parse_command(text, ["Alpha", "Bravo"], list(waypoints.keys()))
    results = []
    for cmd in parsed.commands:
        action, msg = iff_engine.validate(cmd)
        if action == "BLOCK":
            results.append({"status": "blocked", "message": msg})
        elif action == "CONFIRM":
            pending_confirmations.append(cmd)
            results.append({"status": "needs_confirmation", "message": msg})
        else:
            await command_queues[cmd.target_drone or "alpha"].put(cmd)
            results.append({"status": "executing", "message": msg})
    return {"results": results, "raw": text}

@app.get("/api/status")
async def get_status():
    return {name: state.to_dict() for name, state in drones.items()}
```

### Streamlit frontend skeleton

```python
import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide", page_title="🎯 Drone C2")
st_autorefresh(interval=2000, key="refresh")

API = "http://localhost:8000"
status = requests.get(f"{API}/api/status").json()

left, center, right = st.columns([1, 2, 1])

with left:
    st.subheader("📊 Telemetry")
    for name, data in status.items():
        st.markdown(f"**{name.upper()}**")
        st.metric("Altitude", f"{data['alt']:.1f} m")
        st.metric("Battery", f"{data['battery']:.0%}")
        st.metric("Mode", data["mode"])

with center:
    m = folium.Map(location=[data["lat"], data["lon"]], zoom_start=15)
    # Drone markers, waypoint markers, IFF-colored entity markers
    st_folium(m, height=450, key="map")

with right:
    st.subheader("📋 Command Log")
    for entry in reversed(st.session_state.get("log", [])[-10:]):
        icon = {"executing": "✅", "blocked": "🚫", "needs_confirmation": "⚠️"}
        with st.chat_message("assistant", avatar=icon.get(entry["status"], "📌")):
            st.markdown(f"`{entry['message']}`")

if prompt := st.chat_input("🎤 Type command or speak via push-to-talk..."):
    resp = requests.post(f"{API}/api/command", json={"command": prompt}).json()
    st.session_state.setdefault("log", []).extend(resp["results"])
```

**IFF color coding on the map**: Green markers for FRIENDLY, orange for UNKNOWN, red for HOSTILE. Use `folium.Icon(color="green", icon="user", prefix="fa")` for entity markers. Blue flag icons for waypoints. Dark blue plane icons for drones.

---

## What to pre-build vs. what waits until event day

Everything below the dashed line touches event-specific data and must wait.

**Pre-build completely** (the night before, on your RTX 4080 machine):

- faster-whisper model download and transcription pipeline
- Complete Pydantic command schemas and Instructor parser
- IFF safety engine logic (all rules, confirmation flow)
- MAVSDK `DroneController` wrapper class with all operations
- `MockDroneController` for testing without SITL
- FastAPI backend with all endpoints and WebSocket handlers
- Streamlit dashboard with map, telemetry, command log, confirmations
- Browser HTML/JS for Web Speech API push-to-talk
- TTS feedback via browser `SpeechSynthesis` API (not pyttsx3 — it's blocking and breaks asyncio)
- Filler word filter ("um", "uh", "like", "so", "you know")
- Docker-compose for local ArduPilot SITL testing

**Test with local ArduPilot SITL** using Docker:
```bash
docker run -d -p 5760:5760 --name alpha radarku/ardupilot-sitl
docker run -d -p 5770:5760 --name bravo -e INSTANCE=1 radarku/ardupilot-sitl
```

---

**Must wait until event day** (inject into config files):

- Waypoint coordinates from the provided waypoints file
- Entity list from the provided JSON
- SITL connection addresses and ports from the cloud VM
- Any event-specific scenario parameters

Use a single `config.yaml` that gets filled in during the first 30 minutes:
```yaml
sitl:
  alpha: {address: "udp://:14550", grpc_port: 50051}
  bravo: {address: "udp://:14560", grpc_port: 50052}
waypoints: {}   # Filled from event file
entities_path: "entities.json"  # Copied from event data
```

---

## Async state management prevents conflicting commands

Each drone has its own **asyncio.Queue** for sequential command execution, plus a state machine that blocks invalid transitions (e.g., can't navigate while landing).

```python
VALID_TRANSITIONS = {
    "idle": ["arming"],
    "arming": ["armed", "idle"],
    "armed": ["taking_off", "idle"],
    "taking_off": ["in_flight"],
    "in_flight": ["navigating", "landing", "returning"],
    "navigating": ["in_flight", "landing", "returning"],
    "landing": ["idle"],
    "returning": ["landing"],
}

async def command_worker(callsign: str):
    """Process commands one at a time per drone."""
    while True:
        cmd = await command_queues[callsign].get()
        try:
            if not can_transition(drones[callsign].state, cmd):
                broadcast(f"Cannot {cmd.command_type} while {drones[callsign].state}")
                continue
            await execute_command(drones[callsign], cmd)
        except ActionError as e:
            broadcast(f"[{callsign}] Error: {e}")
        finally:
            command_queues[callsign].task_done()
```

Run telemetry streams as concurrent `asyncio.create_task()` background tasks — one per telemetry type (position, battery, flight mode, armed status, in-air status) per drone. Store readings in a shared `DroneState` dataclass that the `/api/status` endpoint returns.

---

## Six-hour execution timeline

| Time | Focus | Deliverable |
|------|-------|-------------|
| 0:00–0:30 | Setup: install deps, get VM creds, test SITL connection | Both drones responding to MAVSDK |
| 0:30–1:00 | Load waypoints + entities into config, verify arm/takeoff/land | Basic drone control working |
| 1:00–2:00 | Wire STT → Parser → IFF → Executor pipeline end-to-end | Voice commands move drones |
| 2:00–2:30 | IFF safety engine with actual entity data | Friendlies blocked, unknowns prompt |
| 2:30–3:00 | Multi-drone commands: "Both drones take off", independent navigation | Concurrent drone operations |
| 3:00–3:30 | Edge cases: ambiguous, contradictory, invalid inputs | Graceful error handling |
| **3:30** | **🛑 FEATURE FREEZE** | **Core system stable** |
| 3:30–4:30 | Bug fixes, edge-case hardening, TTS feedback, query commands | Polish and reliability |
| 4:30–5:30 | Full test with practice dataset, fix failures, test novel scenarios | System passes practice scenarios |
| 5:30–6:00 | Final testing, cleanup | Ready for evaluation |

**Critical rule**: Feature freeze at hour 3.5. Every minute after that goes to reliability, not features. The automated scoring rewards a system that handles 90% of commands correctly over one that handles 60% of commands with flashy extras.

## Winning differentiation beyond minimum requirements

Three high-impact features that take minimal extra code once the core is working:

**TTS audio feedback** uses the browser's built-in `SpeechSynthesis` API — send a text string from FastAPI via WebSocket, and the browser speaks it. Zero server overhead: `speechSynthesis.speak(new SpeechSynthesisUtterance("Alpha taking off to 20 meters"))`. This creates a complete voice-in/voice-out loop that feels like a real C2 system.

**Natural language queries** ("What's Alpha's altitude?", "Where is Bravo?") are already handled by the `QueryCommand` Pydantic type. The LLM parser routes these to a query handler that reads from the cached telemetry state and returns a spoken response. This costs no additional architectural complexity.

**Contextual awareness** is the highest-difficulty differentiator: maintaining a short conversation history in the LLM system prompt enables "do that for Bravo too" and "go higher." Pass the last 3–5 commands as context: `{"role": "assistant", "content": "Executed: NavigateCommand(target_drone='Alpha', waypoint='Charlie')"}`. GPT-4o-mini resolves references like "that" and "there" from context. This is the feature that separates a command parser from a true voice assistant — and it's about 10 extra lines of code to maintain a conversation buffer.

The scoring system tests with **different scenarios than practice data**, which means hardcoded responses fail. The LLM-based parser is inherently generalizable — it handles novel phrasing, unusual parameter values, and unexpected command combinations without any additional code. This is the single strongest argument for the LLM approach over regex: you're buying generalization for free.