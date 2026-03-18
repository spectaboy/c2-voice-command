# Voice-driven C2 for uncrewed systems: complete hackathon blueprint

**Build a multi-domain voice command-and-control system in 7 days using 5 parallel Claude Code instances, ArduPilot SITL, and the TAK ecosystem — and win.** This specification provides every command, code snippet, file, schema, and schedule needed to go from zero to a working demo that commands UAVs, UGVs, and a USV via voice on a shared ATAK map. The architecture mirrors the hierarchical approach proven by Primordial Labs' founders at DARPA's AlphaDogfight Trials, reimplemented as an open-source Claude tool-calling pipeline over CoT/TAK — directly aligned with what the CAF is deploying today and the DoD's $100M DIU Autonomous Vehicle Orchestrator challenge validated last January.

---

## Question 1: Function-specialized agents win this hackathon

**Option A (function-specialized) is the correct architecture**, and the analysis is definitive for this prompt. Here is why each option fails or succeeds.

**Option B (domain-specialized) loses** because ArduPilot uses identical MAVLink protocol across Copter, Rover, and Rover-as-boat. Building separate UAV/UGV/USV agents means triplicating the same MAVLink command logic, the same CoT generation, and the same voice parsing — with three times the integration risk. The "multi-domain" requirement is actually a configuration parameter change (`-v ArduCopter` vs `-v Rover` vs `-v Rover -f motorboat`), not an architectural boundary.

**Option C (single domain) loses** because the prompt explicitly requires air/land/maritime coverage. Military hackathon judges at NATO TIDE and Canada's Icebreaker consistently reward breadth with operational narrative over single-domain depth. Showing 3 domains at 80% beats 1 domain at 100%.

**Option A wins** because each function in the pipeline — voice transcription, NLU parsing, vehicle abstraction, CoT/TAK bridging, dashboard rendering — is genuinely distinct technology requiring different expertise. The vehicle abstraction layer treats domain differences as data, not code. Adding a USV is a config entry, not a new service.

### How Primordial Labs' hierarchical RL translates to this architecture

The Pope et al. paper ("Hierarchical Reinforcement Learning for Air Combat at DARPA's AlphaDogfight Trials," IEEE Transactions on AI, Vol 4 Issue 6, 2023) describes a **two-level architecture**: a high-level SAC-trained policy selector observes full state and chooses among low-level specialized policies, each trained for specific engagement regions. The mapping to your system is precise:

| AlphaDogfight RL | Your C2 System |
|---|---|
| High-level policy selector (SAC) | Claude with tool-calling as coordinator |
| Low-level specialized policies | Domain-specific tool functions (`move_uav()`, `patrol_ugv()`, `deploy_usv()`) |
| State observation → policy selection | NLU intent extraction → function routing |
| Reward shaping from expert knowledge | System prompt with military doctrine constraints |
| Modular policy addition | New tool function = new capability |
| Off-policy experience replay | Command log + few-shot correction history |

**Do not implement RL-based routing.** For a hackathon, Claude's native tool-calling is the high-level policy selector. It already performs intent classification and function routing with zero training. The RL parallel is conceptual and narrative — use it in the pitch, not the code. Recent academic work (HierRouter 2025, Router-R1 2025) validates this mapping, but those systems require training infrastructure you don't have time for. Claude's tool-calling achieves **functionally equivalent routing** through in-context learning and structured output.

---

## Question 2: Claude Code parallel setup — exact commands

### Step 1: Initialize the main repo

```bash
mkdir c2-voice-command && cd c2-voice-command
git init
npm init -y  # or poetry init for Python
# Create the shared scaffold
mkdir -p src/{voice,nlu,coordinator,vehicles,tak,iff,dashboard,shared}
mkdir -p tests scripts docker
touch CLAUDE.md .gitignore
```

### Step 2: Create git worktrees (two methods)

**Method A — Native `--worktree` flag (Claude Code v2.1.49+, recommended):**

Open 5 terminal tabs, one per person:

```bash
# Terminal 1 — Voice/ASR pipeline
claude -w voice-asr "Build the real-time voice transcription service using faster-whisper"

# Terminal 2 — NLU/Coordinator
claude -w nlu-coordinator "Build the NLU command parser and coordinator service using Claude API tool-calling"

# Terminal 3 — Vehicle/MAVLink bridge
claude -w vehicle-bridge "Build the MAVLink vehicle abstraction layer and ArduPilot SITL bridge"

# Terminal 4 — TAK/CoT/IFF integration
claude -w tak-iff "Build the CoT/TAK bridge, FreeTAKServer integration, and IFF classification engine"

# Terminal 5 — Dashboard/UI
claude -w dashboard "Build the React tactical dashboard with Leaflet map and WebSocket real-time updates"
```

This creates `.claude/worktrees/{name}/` directories, each on its own branch (`worktree-voice-asr`, etc.), sharing the same `.git` database.

**Method B — Manual worktrees:**

```bash
git worktree add ../c2-voice-asr -b feature/voice-asr
git worktree add ../c2-nlu-coordinator -b feature/nlu-coordinator
git worktree add ../c2-vehicle-bridge -b feature/vehicle-bridge
git worktree add ../c2-tak-iff -b feature/tak-iff
git worktree add ../c2-dashboard -b feature/dashboard

# Then start Claude Code in each:
cd ../c2-voice-asr && claude
cd ../c2-nlu-coordinator && claude
# etc.
```

### Step 3: Folder structure

```
c2-voice-command/                    # Main worktree (main branch)
├── .git/
├── .claude/
│   ├── worktrees/                   # Auto-created by --worktree
│   │   ├── voice-asr/
│   │   ├── nlu-coordinator/
│   │   ├── vehicle-bridge/
│   │   ├── tak-iff/
│   │   └── dashboard/
│   ├── settings.json
│   └── commands/
│       └── merge-worktree.md        # Custom slash command
├── CLAUDE.md                        # Root shared context
├── src/
│   ├── shared/                      # API CONTRACTS — frozen after Day 1
│   │   ├── schemas.py               # Pydantic models
│   │   ├── constants.py             # Ports, type strings, callsigns
│   │   └── interfaces.py            # Abstract base classes
│   ├── voice/                       # Person 1 owns
│   ├── nlu/                         # Person 2 owns
│   ├── coordinator/                 # Person 2 owns
│   ├── vehicles/                    # Person 3 owns
│   ├── tak/                         # Person 4 owns
│   ├── iff/                         # Person 4 owns
│   └── dashboard/                   # Person 5 owns
├── docker/
│   └── docker-compose.yml
├── scripts/
│   ├── start-sitl.sh
│   └── start-all.sh
└── tests/
```

### Step 4: Preventing file conflicts

Each worktree owns specific directories. Add to each worktree's CLAUDE.md:

```markdown
## Scope
You own ONLY files in src/voice/. Do NOT modify files outside this directory.
If you need a new shared type, describe it and the human will add it to src/shared/.
```

The root `src/shared/` directory is modified only on `main` by the integration lead (Person 2), then rebased into all worktrees:

```bash
# In each worktree, pull shared updates:
git fetch origin main && git rebase origin/main
```

### Step 5: Merging worktrees back

```bash
# From main branch:
git checkout main
git merge worktree-voice-asr          # Merge one at a time
git merge worktree-nlu-coordinator
git merge worktree-vehicle-bridge
git merge worktree-tak-iff
git merge worktree-dashboard

# Or via GitHub PRs (recommended):
gh pr create --base main --head worktree-voice-asr --title "feat: voice ASR pipeline"
```

### Step 6: Coordination via shared API contracts

**This is the most critical step.** Before anyone writes a line of feature code, Person 2 commits this to `src/shared/schemas.py`:

```python
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime

class Domain(str, Enum):
    AIR = "air"
    GROUND = "ground"
    MARITIME = "maritime"

class Affiliation(str, Enum):
    FRIENDLY = "f"
    HOSTILE = "h"
    UNKNOWN = "u"
    NEUTRAL = "n"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class CommandType(str, Enum):
    MOVE = "move"
    RTB = "rtb"
    LOITER = "loiter"
    PATROL = "patrol"
    OVERWATCH = "overwatch"
    ENGAGE = "engage"
    CLASSIFY = "classify"
    STATUS = "status"

class Location(BaseModel):
    lat: float
    lon: float
    alt_m: float = 0.0
    grid_ref: Optional[str] = None

class MilitaryCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    command_type: CommandType
    vehicle_callsign: str
    domain: Domain
    location: Optional[Location] = None
    parameters: dict = {}
    raw_transcript: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class VehicleStatus(BaseModel):
    uid: str
    callsign: str
    domain: Domain
    affiliation: Affiliation
    lat: float
    lon: float
    alt_m: float
    heading: float
    speed_mps: float
    battery_pct: float = 100.0
    mode: str = "GUIDED"
    armed: bool = False

class IFFAssessment(BaseModel):
    uid: str
    affiliation: Affiliation
    confidence: float
    threat_score: float
    indicators: List[str]
    timestamp: str

class CoTEvent(BaseModel):
    uid: str
    cot_type: str          # e.g., "a-f-A-M-F-Q-r"
    lat: float
    lon: float
    alt_m: float
    callsign: str
    heading: float = 0.0
    speed_mps: float = 0.0
    stale_seconds: int = 30

class WSMessage(BaseModel):
    type: str              # "position_update" | "iff_change" | "command_ack" | "voice_transcript"
    payload: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

And `src/shared/constants.py`:

```python
# Service ports
VOICE_PORT = 8001
NLU_PORT = 8002
COORDINATOR_PORT = 8000
MAVLINK_BRIDGE_PORT = 8003
IFF_PORT = 8004
WS_PORT = 8005
DASHBOARD_PORT = 3000
FTS_COT_PORT = 8087
FTS_REST_PORT = 19023
FTS_WEBUI_PORT = 5000

# SITL vehicles — port = 5760 + (instance * 10)
VEHICLES = {
    "UAV-1": {"sitl_port": 5760, "sysid": 1, "type": "ArduCopter", "cot_type": "a-f-A-M-F-Q-r", "domain": "air"},
    "UAV-2": {"sitl_port": 5770, "sysid": 2, "type": "ArduCopter", "cot_type": "a-f-A-M-F-Q-r", "domain": "air"},
    "UAV-3": {"sitl_port": 5780, "sysid": 3, "type": "ArduCopter", "cot_type": "a-f-A-M-F-Q-r", "domain": "air"},
    "UGV-1": {"sitl_port": 5790, "sysid": 4, "type": "Rover",      "cot_type": "a-f-G-E-V",     "domain": "ground"},
    "UGV-2": {"sitl_port": 5800, "sysid": 5, "type": "Rover",      "cot_type": "a-f-G-E-V",     "domain": "ground"},
    "USV-1": {"sitl_port": 5810, "sysid": 6, "type": "Rover",      "cot_type": "a-f-S-X",       "domain": "maritime", "frame": "motorboat"},
}

# CoT type strings (MIL-STD-2525)
COT_TYPES = {
    ("air", "f"):      "a-f-A-M-F-Q-r",   # Friendly UAV
    ("air", "h"):      "a-h-A-M-F-Q-r",   # Hostile UAV
    ("air", "u"):      "a-u-A",            # Unknown air
    ("ground", "f"):   "a-f-G-E-V",        # Friendly ground vehicle
    ("ground", "h"):   "a-h-G-E-V",        # Hostile ground vehicle
    ("ground", "u"):   "a-u-G",            # Unknown ground
    ("maritime", "f"): "a-f-S-X",           # Friendly surface vessel
    ("maritime", "h"): "a-h-S-X",           # Hostile surface vessel
    ("maritime", "u"): "a-u-S",             # Unknown sea surface
}
```

---

## Question 3: The learning system — pragmatic hackathon approach

### Fine-tuning Whisper: yes, but run it in background

**The verdict: start with prompt engineering, fine-tune in parallel.** Here is the exact decision matrix:

**Hour 0–1 (immediate):** Deploy base `whisper-large-v3-turbo` via faster-whisper with military vocabulary in `initial_prompt`. This gets you 85% accuracy on standard military terms instantly. faster-whisper's `hotwords` parameter provides additional biasing:

```python
segments, info = model.transcribe(
    audio,
    language="en",
    initial_prompt="Military radio. Grid coordinates, callsigns Bravo Alpha. "
                   "Terms: overwatch, exfil, RTB, bingo fuel, CASEVAC, WILCO, "
                   "Lima Charlie, niner for nine.",
    hotwords="overwatch exfil RTB bingo CASEVAC WILCO niner",
    vad_filter=True,
    beam_size=5,
)
```

**Hour 1–2 (parallel):** Generate **1,000+ synthetic training samples** using Edge TTS with military sentences across 6 voice variants, augmented with audiomentations (radio bandpass filter at 200–4000 Hz, Gaussian noise for static, background engine noise, clipping distortion for overdriven comms). The pipeline generates ~1,050 samples in 30 minutes.

**Hour 2–5 (unattended GPU job):** LoRA fine-tune on your A100 or RTX 4090. QLoRA (4-bit quantization) fits in **6–8 GB VRAM** for whisper-large-v3-turbo. Training 500 steps with batch size 4 and gradient accumulation 4 completes in **1–2 hours on A100**. The LoRA checkpoint is ~60 MB versus 7 GB for the full model.

```python
# Key LoRA config for Whisper turbo
lora_config = LoraConfig(
    r=32, lora_alpha=64,
    target_modules=["q_proj", "v_proj", "k_proj", "out_proj", "fc1", "fc2"],
    lora_dropout=0.05, bias="none"
)
# Freeze encoder, train only decoder LoRA adapters
model.model.encoder.requires_grad_(False)
```

**Hour 5+:** Swap in fine-tuned model. The rest of the team never noticed — they were building the C2 pipeline against base Whisper the whole time.

### How the system gets smarter each run

The learning system is a **dynamic prompt builder**, not an RL agent. It works through three mechanisms:

1. **Correction logging**: When the operator corrects a misparse ("No, I said grid niner-seven-two, not nine-seven-two"), the system stores the `(wrong_transcription, correct_command)` pair and injects it as a few-shot example into the LLM's system prompt for all subsequent commands.

2. **Context window**: The last 10–20 successful commands stay in the LLM's context, so "advance to next checkpoint" resolves correctly when the system knows the unit's current position and mission.

3. **Whisper prompt chaining**: Frequently misheard terms get appended to Whisper's `initial_prompt` at runtime, improving transcription accuracy within the same session.

This is not RL. It is **in-context learning with persistent state** — functionally equivalent for a demo, implementable in an afternoon, and honestly more reliable than a trained router for a 7-day prototype.

---

## Question 4: Exact CLAUDE.md files for every agent

### Root CLAUDE.md (shared by all worktrees)

```markdown
# Military Voice-Driven C2 System — Hackathon Project

## Mission
Build a voice-driven Command & Control system for uncrewed air, ground, and
maritime vehicles. Operator speaks natural language → system parses into
structured commands → vehicles execute in ArduPilot SITL → positions update
on TAK map via Cursor-on-Target protocol.

## Tech Stack
- Python 3.11+, FastAPI for all services
- faster-whisper for ASR, Claude API for NLU (tool-calling)
- pymavlink for ArduPilot SITL control
- pytak for CoT/TAK integration
- React + Vite + Leaflet for dashboard
- WebSocket (fastapi-websocket) for real-time updates
- Docker Compose for FreeTAKServer

## Architecture
Voice (:8001) → NLU (:8002) → Coordinator (:8000) → MAVLink Bridge (:8003) → SITL (:5760+)
                                     ↕                        ↓
                              IFF Engine (:8004)    CoT Bridge → FTS (:8087)
                                     ↓                        ↓
                              WebSocket (:8005) ←──────── Dashboard (:3000)

## Critical Rules
- ALL shared types are in src/shared/schemas.py — this is the single source of truth
- NEVER modify src/shared/ without explicit human approval
- Every service must use the Pydantic models from src/shared/schemas.py
- Services communicate via HTTP REST for commands, WebSocket for real-time streams
- All Python code: type hints required, async/await preferred, black formatting
- Run `pytest tests/` before every commit
- Commit messages: conventional commits (feat:, fix:, test:)

## Vehicle Configuration
See src/shared/constants.py for all vehicle definitions, ports, and CoT type strings.
Six vehicles: 3 UAVs (ArduCopter), 2 UGVs (Rover), 1 USV (Rover motorboat frame).

## Commands
- `./scripts/start-sitl.sh` — Launch all 6 SITL instances
- `./scripts/start-all.sh` — Launch all services
- `docker compose up -d` — Start FreeTAKServer
- `pytest tests/ -v` — Run all tests
```

### /worktrees/voice-asr/CLAUDE.md

```markdown
# Voice ASR Agent — You own src/voice/

## Your Responsibility
Build the real-time voice transcription service. Microphone → Whisper → text.

## Scope
- ONLY modify files in src/voice/ and tests/test_voice/
- Your service runs on port 8001

## Requirements
1. FastAPI service with two modes:
   - POST /transcribe — accepts audio file, returns text (for testing)
   - WebSocket /ws/voice — streams audio chunks, returns transcriptions
2. Use faster-whisper with whisper-large-v3-turbo model
3. Implement Silero VAD for speech endpoint detection
4. Push-to-talk mode (primary) + continuous listening with VAD (secondary)
5. Military vocabulary in initial_prompt (see src/shared/constants.py)
6. Output: {"transcript": str, "confidence": float, "timestamp": str}
7. Emit transcript to WebSocket server at ws://localhost:8005 for dashboard

## Key Libraries
- faster-whisper, silero-vad (via torch.hub), sounddevice, numpy
- FastAPI, uvicorn, websockets

## DO NOT
- Modify src/shared/ — use the schemas as-is
- Build NLU/command parsing — that's the NLU agent's job
- Touch any files outside src/voice/ and tests/test_voice/
```

### /worktrees/nlu-coordinator/CLAUDE.md

```markdown
# NLU & Coordinator Agent — You own src/nlu/ and src/coordinator/

## Your Responsibility
Parse natural language military commands into MilitaryCommand Pydantic objects,
route them to the correct vehicle, and enforce confirmation safeguards.

## Scope
- ONLY modify src/nlu/, src/coordinator/, and tests/test_nlu/
- NLU runs on port 8002, Coordinator on port 8000

## Requirements
1. NLU Service (port 8002):
   - POST /parse — accepts {"transcript": str}, returns MilitaryCommand
   - Use Claude API with tool-calling: define tools for each CommandType
   - Tools: move_vehicle, return_to_base, set_overwatch, patrol_route,
     classify_contact, request_status, loiter_at
   - Extract: callsign, command type, location (lat/lon or grid ref), parameters
   - Handle ambiguity: "send the drone" → resolve to which UAV based on context

2. Coordinator Service (port 8000):
   - POST /command — accepts MilitaryCommand, validates, routes to vehicle bridge
   - Risk assessment: LOW (navigation) → execute; MEDIUM (RTB) → execute with notice;
     HIGH/CRITICAL (engage, weapons) → require voice confirmation
   - Confirmation flow: return readback text → voice agent speaks it → operator
     confirms/cancels → coordinator executes or aborts
   - POST /confirm/{command_id} — handle confirmation responses
   - GET /status — return all vehicle statuses

3. Learning system:
   - Log all commands to command_log.json
   - Track corrections as few-shot examples
   - Build dynamic system prompt from correction history
   - Maintain context window of last 20 successful commands

## Key Integration Points
- Receives text from Voice ASR (port 8001)
- Sends MilitaryCommand to Vehicle Bridge (port 8003)
- Sends IFF classify commands to IFF Engine (port 8004)
- Broadcasts command events via WebSocket (port 8005)
```

### /worktrees/vehicle-bridge/CLAUDE.md

```markdown
# Vehicle & MAVLink Bridge Agent — You own src/vehicles/

## Your Responsibility
Abstract ArduPilot SITL vehicles behind a unified API. Translate MilitaryCommand
objects into MAVLink messages. Read telemetry. Generate CoT XML for TAK.

## Scope
- ONLY modify src/vehicles/ and tests/test_vehicles/
- Service runs on port 8003

## Requirements
1. Vehicle Abstraction Layer:
   - VehicleManager class: connect to all 6 SITL instances via pymavlink
   - Unified interface: move_to(callsign, lat, lon, alt), rtb(callsign),
     set_mode(callsign, mode), arm(callsign), get_status(callsign)
   - Handle ArduCopter (takeoff/land), Rover (navigate), Boat (navigate on water)

2. MAVLink Bridge (port 8003):
   - POST /execute — accepts MilitaryCommand, translates to MAVLink, sends to SITL
   - GET /telemetry — returns all VehicleStatus objects
   - WebSocket /ws/telemetry — streams position updates at 1 Hz

3. CoT Generation:
   - Convert each vehicle's GLOBAL_POSITION_INT to CoT XML
   - Use correct type strings from src/shared/constants.py
   - Send CoT to FreeTAKServer TCP port 8087 at 1 Hz
   - Handle IFF reclassification: change CoT type string affiliation character

4. SITL Connection Strings:
   - tcp:127.0.0.1:5760 through tcp:127.0.0.1:5810 (increments of 10)

## Key MAVLink Messages
- Send: SET_POSITION_TARGET_GLOBAL_INT, COMMAND_LONG (arm/mode/takeoff)
- Read: GLOBAL_POSITION_INT, HEARTBEAT, VFR_HUD, BATTERY_STATUS

## DO NOT
- Handle voice/NLU — you receive structured MilitaryCommand objects
- Modify src/shared/
```

### /worktrees/tak-iff/CLAUDE.md

```markdown
# TAK/CoT & IFF Agent — You own src/tak/ and src/iff/

## Your Responsibility
Build the IFF classification engine and any additional TAK/CoT logic
beyond the vehicle bridge's basic CoT generation.

## Scope
- ONLY modify src/tak/, src/iff/, and tests/test_iff/
- IFF Engine runs on port 8004

## Requirements
1. IFF Classification Engine (port 8004):
   - POST /classify — accepts entity position data, returns IFFAssessment
   - POST /manual-classify — operator manually classifies a contact
   - GET /contacts — return all tracked contacts with classifications
   - WebSocket /ws/iff — stream IFF assessment updates

2. Behavioral IFF Rules:
   - Intercept course detection (heading within 25° of bearing to friendly)
   - Closing speed calculation (positive = approaching)
   - Time-to-intercept estimation
   - Proximity alerting (<500m critical, <2km warning)
   - Loitering detection near sensitive areas (>5 min within defined radius)
   - High speed anomaly (>108 km/h for ground contacts)

3. IFF → CoT Integration:
   - When classification changes, update CoT type string affiliation character:
     f→h: "a-f-G-E-V" becomes "a-h-G-E-V"
   - Maintain audit trail: every classification change logged with timestamp,
     previous/new affiliation, confidence, triggering indicators
   - Push updated CoT to FreeTAKServer

4. Simulated Hostile Contacts:
   - Create 2-3 simulated "unknown" contacts that move on predefined paths
   - One approaches friendly forces (triggers hostile classification)
   - One loiters near sensitive area (triggers suspect classification)
   - These are NOT SITL vehicles — just simulated CoT positions

## Key Math
- Haversine distance, forward azimuth bearing, closing speed projection
- All in src/iff/geometry.py — pure Python, no external geo libraries needed
```

### /worktrees/dashboard/CLAUDE.md

```markdown
# Dashboard Agent — You own src/dashboard/

## Your Responsibility
Build the React tactical dashboard showing map, vehicle status, IFF audit trail,
voice transcript, and command confirmation UI.

## Scope
- ONLY modify src/dashboard/ and tests/test_dashboard/
- Runs on port 3000

## Requirements
1. React + Vite + TypeScript application
2. Layout: 4-panel split screen
   - TOP LEFT (60%): Leaflet map with vehicle markers (military dark theme)
   - TOP RIGHT (40%): Vehicle status cards (callsign, mode, battery, speed)
   - BOTTOM LEFT (50%): Voice transcript log (scrolling, with parsed command)
   - BOTTOM RIGHT (50%): IFF audit trail + command confirmation panel

3. Map:
   - CartoDB dark_all basemap for military look
   - Vehicle markers colored by affiliation: green=friendly, red=hostile, yellow=unknown
   - Shape by domain: rotated diamond=air, rectangle=ground, lozenge=sea
   - Vehicle trails (last 30 positions as polyline)
   - Click vehicle → show detail popup with all telemetry

4. WebSocket Integration:
   - Connect to ws://localhost:8005/ws
   - Handle message types: position_update, iff_change, command_ack, voice_transcript,
     confirmation_required
   - When confirmation_required: show modal with readback text and CONFIRM/CANCEL buttons

5. Visual Style:
   - Military dark theme: #0a0e14 background, monospace font, uppercase headers
   - Green accent (#00ff88) for friendly, red (#ff3333) for hostile
   - Scanning line animation on header (subtle)
   - "UNCLASSIFIED" banner top and bottom (required for military demos)

## DO NOT
- Build any backend logic — consume WebSocket data only
- Modify src/shared/
```

---

## Question 5: Complete technical architecture — the full data flow

### Service map with all ports

```
┌─────────────────────────────────────────────────────────────────────┐
│  OPERATOR                                                            │
│  [Microphone] ──push-to-talk──→ [Voice ASR :8001]                   │
│  [Speaker]    ←──TTS response── [Edge TTS]                          │
│  [Browser]    ←──────────────── [Dashboard :3000]                    │
└─────────────────────────────────────────────────────────────────────┘
         │ audio stream (WebSocket)              │ HTTP
         ▼                                       ▼
┌─────────────────┐    POST /parse    ┌─────────────────────┐
│  Voice ASR       │ ───────────────→ │  NLU Parser          │
│  :8001           │    {transcript}   │  :8002               │
│  faster-whisper  │                   │  Claude API          │
│  + Silero VAD    │                   │  tool-calling        │
└─────────────────┘                   └──────────┬──────────┘
                                                  │ MilitaryCommand
                                                  ▼
                                      ┌─────────────────────┐
                                      │  Coordinator         │
                                      │  :8000               │
                                      │  Risk assessment     │
                                      │  Confirmation flow   │
                                      │  Command routing     │
                                      └───┬─────────┬───────┘
                                          │         │
                        POST /execute     │         │ POST /classify
                                          ▼         ▼
                              ┌───────────────┐ ┌──────────────┐
                              │ Vehicle Bridge │ │ IFF Engine    │
                              │ :8003          │ │ :8004         │
                              │ pymavlink      │ │ Rules engine  │
                              │ CoT generator  │ │ Contact track │
                              └───┬───────────┘ └──────┬───────┘
                                  │ MAVLink              │ CoT type
                                  ▼                      │ changes
         ┌────────────────────────────────────┐          │
         │  ArduPilot SITL (6 instances)      │          │
         │  :5760 UAV-1  :5770 UAV-2          │          │
         │  :5780 UAV-3  :5790 UGV-1          │          │
         │  :5800 UGV-2  :5810 USV-1          │          │
         └────────────────────────────────────┘          │
                    │ GLOBAL_POSITION_INT                 │
                    ▼                                     ▼
         ┌──────────────────────────────────────────────────┐
         │  CoT Bridge (inside Vehicle Bridge)               │
         │  pymavlink telemetry → CoT XML                    │
         │  IFF updates → CoT type string change             │
         └──────────────────┬───────────────────────────────┘
                            │ TCP :8087 (CoT XML)
                            ▼
                  ┌──────────────────┐        ┌──────────────┐
                  │ FreeTAKServer     │ ←────→ │ ATAK Client   │
                  │ CoT:  :8087       │        │ (Android/PC)  │
                  │ REST: :19023      │        │ All 6 vehicles │
                  │ Web:  :5000       │        │ on one map     │
                  └──────────────────┘        └──────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────────────────┐
         │  WebSocket Hub (:8005)                            │
         │  Aggregates: telemetry, IFF, commands, voice      │
         │  Broadcasts: WSMessage to all dashboard clients   │
         └──────────────────┬───────────────────────────────┘
                            │ ws://localhost:8005/ws
                            ▼
                  ┌──────────────────┐
                  │ React Dashboard   │
                  │ :3000             │
                  │ Leaflet map       │
                  │ Status + IFF log  │
                  └──────────────────┘
```

### End-to-end flow: "Alpha UAV, proceed to grid 447, establish overwatch"

1. **Microphone → Voice ASR (:8001)**: Operator presses push-to-talk key. Audio streams via WebSocket to faster-whisper. Silero VAD detects speech end after 750ms silence. Whisper transcribes: `"Alpha UAV proceed to grid four four seven establish overwatch"`. Confidence: 0.94.

2. **Voice ASR → NLU (:8002)**: HTTP POST `{"transcript": "Alpha UAV proceed to grid four four seven establish overwatch", "confidence": 0.94}`. Claude API with tool-calling resolves: tool `set_overwatch` with arguments `{callsign: "UAV-1", grid_ref: "447", lat: 38.912, lon: -77.031, alt_m: 100}`.

3. **NLU → Coordinator (:8000)**: Returns `MilitaryCommand(command_type=OVERWATCH, vehicle_callsign="UAV-1", domain=AIR, location=Location(lat=38.912, lon=-77.031, alt_m=100))`. Risk assessment: **LOW** (navigation only). No confirmation required.

4. **Coordinator → Vehicle Bridge (:8003)**: POST `/execute` with the MilitaryCommand. Bridge resolves UAV-1 → SITL port 5760. Sends MAVLink `SET_POSITION_TARGET_GLOBAL_INT` with latitude, longitude, altitude. Sets mode to GUIDED if not already.

5. **SITL (:5760) → CoT Bridge**: Vehicle begins moving. Bridge reads `GLOBAL_POSITION_INT` at 1 Hz, constructs CoT XML:
```xml
<event version="2.0" uid="SITL-UAV-01" type="a-f-A-M-F-Q-r" how="m-g"
       time="2026-03-17T14:30:00Z" start="2026-03-17T14:30:00Z"
       stale="2026-03-17T14:30:30Z">
  <point lat="38.9120" lon="-77.0310" hae="100.0" ce="5.0" le="5.0"/>
  <detail>
    <contact callsign="UAV-1"/>
    <track course="045.0" speed="15.0"/>
  </detail>
</event>
```

6. **CoT → FreeTAKServer (:8087)**: Raw XML sent over TCP. FTS distributes to all connected TAK clients.

7. **ATAK map**: UAV-1 icon (friendly air symbol, cyan/green) moves to new position. Trail line shows movement path.

8. **WebSocket (:8005) → Dashboard (:3000)**: Position update broadcast. Map marker moves. Status card updates speed/heading. Voice transcript panel shows the command and its parsed interpretation.

### What runs in Docker vs. natively

| Component | Docker | Native | Why |
|---|---|---|---|
| FreeTAKServer | ✅ | | Pre-built image, complex dependencies |
| ArduPilot SITL (×6) | | ✅ | Timing-sensitive, needs UDP networking |
| Voice ASR | | ✅ | GPU access needed for Whisper |
| NLU/Coordinator | | ✅ | Simple FastAPI, needs Claude API key |
| Vehicle Bridge | | ✅ | Needs localhost access to SITL ports |
| IFF Engine | | ✅ | Simple FastAPI |
| Dashboard | Either | ✅ | `npm run dev` is simpler for development |

---

## Question 6: Using the Primordial Labs paper — the winning narrative

### How to cite and reference it

**Yes, cite it explicitly.** The paper is peer-reviewed IEEE ("Hierarchical Reinforcement Learning for Air Combat at DARPA's AlphaDogfight Trials," IEEE Trans. AI, Vol 4, Issue 6, pp. 1371–1385, Dec 2023). The first author (Adrian Pope) and a co-author (Lee Ritholtz) are Primordial Labs' CTO and CEO respectively. Their team placed **2nd of 8 competitors** at the DARPA AlphaDogfight Trials and **defeated a USAF F-16 Weapons Instructor Course graduate 5-0**.

### The architectural parallel that makes judges care

Frame it as: "The same architectural principle that won AlphaDogfight — a high-level policy coordinator dynamically selecting among specialized low-level executors — is what our system implements through Claude's tool-calling architecture. Where Pope et al. used SAC-trained neural networks to select combat maneuver policies, we use a frontier LLM to select among domain-specific command functions. The high-level reasoning is more general (natural language vs. state vectors), but the hierarchical delegation pattern is identical."

This is technically honest and narratively compelling. The judges see: (a) you've read the literature, (b) you understand the architectural principles behind the competition's most relevant commercial product, (c) your implementation is a principled simplification, not an ad-hoc hack.

### What to say when asked "how is this different from Anura?"

"Primordial Labs proved voice C2 works — they have 8,000 Army licenses across Transformation in Contact brigades and contracts with 4 PEOs. They validated the operational concept. Our contribution is demonstrating this capability can be built on an **open-source, sovereign stack** using off-the-shelf components the CAF already deploys — ArduPilot, TAK/CloudTAK, and standard CoT protocols. Anura is proprietary, US-only, and runs a custom NLU engine with no LLMs. We use a frontier LLM with tool-calling, which gives us zero-shot generalization to novel commands without retraining. Different engineering tradeoffs, same operational thesis. And critically: Anura runs locally with no cloud dependency, which is the right long-term architecture. Our system can transition to on-device inference as edge LLMs mature."

---

## Question 7: Making the simulation demo visually impressive

### Optimal vehicle configuration

Run **6 simulated vehicles**: 3 UAVs + 2 UGVs + 1 USV. This is enough to demonstrate multi-domain coordination without overwhelming SITL or risking demo instability. Launch commands:

```bash
# Terminal per vehicle (or use a script)
sim_vehicle.py -v ArduCopter -I0 --sysid 1 -L CMAC --map --console
sim_vehicle.py -v ArduCopter -I1 --sysid 2 -L CMAC --no-extra-ports
sim_vehicle.py -v ArduCopter -I2 --sysid 3 -L CMAC --no-extra-ports
sim_vehicle.py -v Rover      -I3 --sysid 4 -L CMAC --no-extra-ports
sim_vehicle.py -v Rover      -I4 --sysid 5 -L CMAC --no-extra-ports
sim_vehicle.py -v Rover -f motorboat -I5 --sysid 6 -L CMAC --no-extra-ports
```

ArduPilot SITL **does support surface vessels** — ArduBoat is ArduRover with `FRAME_CLASS=2`, and the `-f motorboat` flag in `sim_vehicle.py` configures this automatically with water-appropriate physics.

### Visual presentation layout

Use a **4-quadrant split screen** on a large monitor or projector:

- **Top-left (60%)**: ATAK map (or Leaflet dashboard map) showing all 6 vehicles with MIL-STD-2525 symbology. UAVs as air track icons (rotated diamonds), UGVs as ground unit rectangles, USV as sea surface lozenge. Friendly in green, hostile contacts in red, unknown in yellow.
- **Top-right (40%)**: Vehicle status cards — callsign, mode (GUIDED/AUTO/RTL), speed, altitude, battery. Color-coded borders.
- **Bottom-left**: Real-time voice transcript — what was said, what was parsed, what command was issued. Shows the "magic" of NLU.
- **Bottom-right**: IFF audit trail and confirmation dialog. When a high-risk command fires, the confirmation modal appears here.

### Four pre-scripted demo scenarios (run in this order)

**Scenario 1 — Multi-domain coordination (2 min)**: "All units, establish harbor defense pattern." UAV-1 takes overwatch altitude, UGV-1 patrols perimeter road, USV-1 moves to harbor entrance. Shows single voice command → three domains respond. Start with this because it's the highest-impact visual.

**Scenario 2 — IFF reclassification (90 sec)**: An unknown contact appears on the map (simulated CoT injection, not SITL). It approaches a friendly UGV. The IFF engine automatically flags it — threat score rises as it gets closer. Operator says: "Classify contact alpha-seven as hostile." CoT type changes from `a-u-G` to `a-h-G`. Icon turns red on map. UAV-2 automatically redirected to track. This demonstrates **behavior-based IFF + voice override + automated response**.

**Scenario 3 — Confirmation safeguard (60 sec)**: Operator says: "Engage hostile contact alpha-seven." System responds via TTS: "CONFIRM: CRITICAL RISK. You are ordering UAV-2 to engage HOSTILE alpha-seven. Say CONFIRM to execute or CANCEL to abort." Operator says: "CONFIRM." System: "Confirmed. Engagement order acknowledged." (In simulation, UAV moves to orbit hostile position.) This shows **human-in-the-loop** for high-risk actions — essential for military judges.

**Scenario 4 — Emergency RTB (30 sec)**: "All units, return to base immediately." All 6 vehicles break current mission and begin RTB. Dramatic, clean ending that shows **safety override capability**.

### Making it look real without hardware

- Use **Gazebo** alongside SITL for 3D visualization of at least one vehicle (the UAV). Even a small window showing a 3D quadcopter flying adds visceral "this is real" energy that TAK maps alone lack.
- Add **sound design**: radio static on voice input, acknowledgment beeps, synthetic TTS responses ("Roger, UAV-1 moving to overwatch position").
- Pre-position SITL vehicles near a **recognizable location** — use a harbor/coastal area as the SITL start location (e.g., `-L 44.6488,-63.5752,0,0` for Halifax Harbor) so the TAK map shows a real coastline.

---

## Question 8: IFF agent — complete technical implementation

### Core geometry calculations

The IFF engine needs four mathematical primitives. All pure Python, no external geo libraries:

**Approach vector detection**: Given an unknown contact and a friendly position, the contact is on an intercept course if its heading is within **25°** of the bearing from the contact to the friendly. The closing speed is calculated by projecting both entities' velocity vectors along the line between them — positive means they're getting closer. Time-to-intercept divides distance by closing speed.

The complete rules-based IFF engine classifies contacts on a **threat score from 0.0 to 1.0** using weighted behavioral indicators:

- Intercept course toward friendly at critical proximity (<500m, closing): **+0.40**
- High-speed approach (>20 m/s closing, <2km): **+0.30**
- Intercept in <60 seconds: **+0.25**
- Inside sensitive area perimeter: **+0.20**
- Loitering near sensitive area >5 minutes: **+0.20**
- Anomalous speed (>108 km/h for ground): **+0.15**

Classification thresholds: **≥0.70 = Hostile**, 0.40–0.69 = Unknown (elevated), 0.20–0.39 = Unknown (low), <0.20 = Neutral. Confidence never reaches 1.0 for hostile — always requires human confirmation for engagement actions.

### Voice command flow: "classify contact alpha-7 as hostile"

1. Whisper transcribes → NLU parses to `MilitaryCommand(command_type=CLASSIFY, parameters={"contact_uid": "alpha-7", "new_affiliation": "hostile"})`
2. Coordinator routes to IFF Engine POST `/manual-classify`
3. IFF Engine updates contact affiliation, generates new CoT type string (e.g., `a-u-G` → `a-h-G`), logs to audit trail
4. CoT Bridge sends updated XML to FreeTAKServer — callsign changes from "UNKNOWN-07" to "HOSTILE-07"
5. WebSocket broadcasts `iff_change` event → dashboard shows red flash on contact marker, audit trail entry appears with operator name, timestamp, previous/new classification

### Why rules-based beats ML for this demo

Rules-based IFF is **transparent, tunable live during the demo, deterministic, requires zero training data, and is implementable in a single afternoon**. Academic IFF research does use CNNs and LSTMs, but those require substantial labeled datasets of contact trajectories. For a hackathon demo, the rules engine provides identical visual impact with none of the training overhead. When judges ask, say: "Rules-based gives us explainability — every classification comes with a list of triggering indicators. An ML model would be a black box. For military use, explainability matters."

---

## Question 9: Seven-day execution plan for 5 people

### Day 1 — Foundation (Monday)

**"Done" = shared interfaces committed, SITL running 6 vehicles, FreeTAKServer up, skeleton services respond on all ports.**

| Person | Task | Claude Code Prompt |
|---|---|---|
| P1 (Lead) | Define schemas, create repo, write root CLAUDE.md, commit shared interfaces | `claude "Initialize the project structure, create all Pydantic schemas in src/shared/schemas.py and constants in src/shared/constants.py per the specification"` |
| P2 (Voice) | Set up faster-whisper, basic transcription endpoint | `claude -w voice-asr "Build src/voice/server.py — FastAPI on port 8001 with POST /transcribe using faster-whisper large-v3-turbo"` |
| P3 (Vehicles) | Install ArduPilot, write SITL launch script, test pymavlink connection | `claude -w vehicle-bridge "Create scripts/start-sitl.sh that launches 6 SITL instances and src/vehicles/mavlink_client.py that connects to all 6 via pymavlink"` |
| P4 (TAK/IFF) | Docker compose for FreeTAKServer, test CoT injection | `claude -w tak-iff "Set up docker/docker-compose.yml for FreeTAKServer and build src/tak/cot_sender.py that sends a test CoT event to port 8087"` |
| P5 (Dashboard) | Scaffold React app, dark theme, Leaflet map rendering | `claude -w dashboard "Create React+Vite+TypeScript app in src/dashboard/ with Leaflet map using CartoDB dark tiles, military CSS theme"` |

**End of Day 1 merge**: P1 merges all branches. Verify: `curl localhost:8001/health`, `curl localhost:8002/health`, all SITL instances visible in MAVProxy, CoT event appears on FreeTAKServer web UI.

### Day 2 — Core services (Tuesday)

**"Done" = voice produces text, text becomes structured commands, one SITL vehicle moves on command.**

| Person | Task |
|---|---|
| P1 | Build NLU service with Claude tool-calling, define all tools |
| P2 | Add Silero VAD, push-to-talk mode, WebSocket streaming |
| P3 | Vehicle abstraction: `move_to()`, `rtb()`, `get_status()` for all vehicle types |
| P4 | IFF engine geometry functions, basic classification rules |
| P5 | WebSocket client in React, vehicle markers on map, status cards |

**End of Day 2 integration test**: Speak "UAV-1, move to grid reference..." → Whisper transcribes → Claude parses → MAVLink sends → SITL vehicle moves. If this works, you're on track.

### Day 3 — End-to-end integration (Wednesday) — HIGHEST RISK DAY

**"Done" = full pipeline voice→map works for all 3 domains.**

| Person | Task |
|---|---|
| P1 | Coordinator service: risk assessment, routing, confirmation flow |
| P2 | TTS response (Edge TTS), voice confirmation loop |
| P3 | CoT bridge: SITL telemetry → CoT XML → FreeTAKServer at 1 Hz |
| P4 | Simulated hostile contacts, IFF auto-classification triggering |
| P5 | IFF audit trail panel, confirmation modal, voice transcript display |

**Critical**: All worktrees merge to main at end of Day 3. Run full integration test. Fix blocking issues before leaving.

### Day 4 — Advanced features (Thursday)

**"Done" = IFF demo works, multi-vehicle voice commands work, TAK shows all entities.**

- P1: Multi-vehicle command parsing ("all units RTB"), context-aware disambiguation
- P2: Whisper fine-tuning (kick off LoRA training, runs overnight if needed)
- P3: Multi-vehicle orchestration (coordinated harbor defense pattern)
- P4: IFF → CoT type string updates, hostile contact auto-tracking
- P5: Map trails, vehicle detail popups, MGRS grid overlay

### Day 5 — Polish and scenarios (Friday)

**"Done" = all 4 demo scenarios work end-to-end at least once.**

- P1: Script all 4 demo scenarios, write exact voice commands
- P2: Swap in fine-tuned Whisper model, test with military vocab
- P3: Performance optimization (reduce voice→action latency)
- P4: Edge cases — what happens when IFF confidence is borderline?
- P5: Final UI polish, scanning line animation, "UNCLASSIFIED" banner

### Day 6 — Integration testing (Saturday)

**"Done" = full demo succeeds 3 of 5 run-throughs without intervention.**

- ALL: Full demo rehearsals (minimum 5 complete runs)
- Bug fix sprint based on failures
- Build fallback modes (keyboard command input if voice fails)
- Record **backup demo video** (absolutely critical safety net)
- Prepare 3-slide architecture overview (problem, solution, architecture diagram)

### Day 7 — Presentation (Sunday)

**"Done" = confident 10-minute live demo with narrative.**

- Morning: Final bug fixes only. **Code freeze at noon.**
- Afternoon: 3 full dress rehearsals with timing
- Prepare answers for expected questions: "How is this different from Anura?" "Would this work in a contested RF environment?" "What about bilingual support?"
- Demo order: multi-domain coordination → IFF reclassification → confirmation safeguard → emergency RTB

### Merge schedule

- **Day 1 end**: Merge all branches (scaffold only, minimal conflict risk)
- **Day 2 end**: Merge + integration test
- **Day 3 end**: **Big merge** — all branches into main. This is the hardest merge.
- **Day 4+**: All work directly on main or very short-lived branches
- **Day 6 noon**: Final merge, branch main to `demo-frozen`

### First commit message

```
feat: initial project scaffold with shared schemas and 6-vehicle SITL config

- Add Pydantic models: MilitaryCommand, VehicleStatus, IFFAssessment, CoTEvent
- Add constants: vehicle config (3 UAV, 2 UGV, 1 USV), ports, CoT type strings
- Add root CLAUDE.md with architecture overview and team coordination rules
- Add scripts/start-sitl.sh for 6-vehicle ArduPilot SITL launch
- Add docker-compose.yml for FreeTAKServer
```

---

## Question 10: The pitch narrative that wins $20,000

### The opening line (memorize this)

"One operator. Three domains. Voice command. Canada has the world's longest coastline, 40% of its territory above the treeline, and 16,500 fewer soldiers than it needs. The math doesn't work without force multiplication."

### The four-beat structure (10 minutes total)

**Beat 1 — The problem (90 sec)**: Canada's Arctic sovereignty requires multi-domain surveillance across 162,000 km of Arctic coastline with roughly 300 permanent northern personnel. Operations NANOOK, LIMPID, and LATITUDE demand persistent ISR that current manning levels cannot sustain. The MQ-9B SkyGuardian drones arriving in 2028 will add capacity, but operator training pipelines are bottlenecked. Primordial Labs has proven voice C2 works for US forces — **8,000 Anura licenses** are now deployed across Army Transformation in Contact brigades, with contracts across 4 PEOs and 5 OEMs. But Anura is proprietary, US-only, and unavailable to the CAF.

**Beat 2 — The solution (90 sec)**: We built an open-source voice C2 pipeline that integrates with CloudTAK — the same platform the CAF already deploys across Regular and Reserve Forces. Our architecture mirrors the hierarchical approach from the DARPA AlphaDogfight Trials (Pope et al., IEEE 2023) — a high-level coordinator dynamically routing to specialized domain executors. But instead of trained RL policies, we use a frontier LLM with tool-calling, giving us zero-shot generalization to any command an operator might speak. The entire stack is sovereign: Whisper for ASR, Claude for NLU, ArduPilot for vehicle control, CoT/TAK for interoperability. No ITAR restrictions. No dependency on US defense contractors.

**Beat 3 — Live demo (4 min)**: Run the four scenarios. Narrate as you go. The visual impact of speaking a command and watching 3 domains respond simultaneously on a TAK map is worth more than any slide.

**Beat 4 — Why this matters (2 min)**: The DoD's DIU launched a **$100M Autonomous Vehicle Orchestrator** prize challenge in January 2026 seeking exactly this capability — voice/text intent translated into coordinated multi-vehicle execution. Primordial Labs has validated the market. The CAF's own RAS doctrine (CADN 24-04, February 2026) states "Robotic and Autonomous Systems are no longer a niche capability — they are a core component of modern land operations." Canada's Defence Industrial Strategy identifies uncrewed autonomous systems as one of 10 sovereign capabilities under the "Build-Partner-Buy" framework. This is an open-source capability that Canada controls, built in 7 days, integrating with infrastructure the CAF already operates. The roadmap: Week 1 was proof of concept. Month 1 is real ArduPilot hardware integration. Month 3 is field testing at CFB Suffield. Month 6 is CloudTAK integration pilot.

### Market validation numbers to cite

- DIU Autonomous Vehicle Orchestrator: **$100M** in total prize awards (January 2026)
- Primordial Labs: **8,000 Army licenses** deployed (March 2025), contracts with **4 PEOs and 5 OEMs**
- Primordial Labs funding: **$2.5–4M** seed from Squadra Ventures + Lockheed Martin Ventures + multiple SBIR awards (note: the $6.6M figure commonly cited could not be confirmed in public sources — use "$multi-million in SBIR contracts and venture funding" instead)
- CAF personnel shortage: up to **16,500 members** below authorized strength
- Canada "Our North, Strong and Free": **$8.1B over 5 years, $73B over 20 years** for Arctic defense
- Canada's Arctic coastline: **162,000 km**, monitored by ~300 permanent northern military personnel

### What CAF-specific angles resonate with judges

**Arctic sovereignty** is the highest-resonance angle. Frame the demo as: "Imagine a single Canadian Ranger at a forward operating hub in Resolute Bay, voice-commanding a UAV for Northwest Passage surveillance, a UGV for perimeter security, and a USV for harbor approach monitoring — all from a satellite-connected tablet running ATAK."

**NATO interoperability** is the second strongest. CoT/TAK is the coalition standard. Canada participated in Bold Quest 19 with ATAK-based digital close air support validated among 70 JTACs from 16 nations. Your system speaks CoT natively — it works with any NATO TAK ecosystem out of the box.

**Bilingual acknowledgment**: Don't promise French support, but acknowledge it: "Whisper supports French transcription natively. Adding bilingual C2 is a configuration change, not an architecture change." CAF judges will note you thought of this.

### What NOT to say

Never claim "production-ready" — say "technology demonstrator." Never dismiss human-in-the-loop — your confirmation safeguard feature IS your answer. Never oversell AI — say "the voice pipeline is 85–90% accurate in clean conditions; we're honest about degradation in contested RF environments, which is why we designed push-to-talk as the primary mode." Never attack Primordial Labs — position them as market validation. And never forget: military judges have operational experience. They can smell overselling from a mile away. Understate capability, let the demo speak.

---

## Summary: what makes this architecture win

The winning insight is that "multi-domain" is an **illusion of complexity**. ArduPilot SITL runs the same MAVLink protocol for copters, rovers, and boats. CoT type strings differ by a single character for air (`A`), ground (`G`), and sea (`S`). The entire "multi-domain" requirement reduces to a lookup table in `src/shared/constants.py`. By building function-specialized services with a clean vehicle abstraction layer, you get all three domains for the cost of one. The hierarchical coordinator pattern — inspired by Primordial Labs' AlphaDogfight architecture, implemented through Claude's tool-calling — provides a principled, citable, and compelling technical narrative. The TAK integration gives you immediate operational relevance with what the CAF is already deploying. And the IFF engine with confirmation safeguards demonstrates the human-in-the-loop thinking that military judges demand.

Five people. Five Claude Code worktrees. Seven days. One voice command that moves air, land, and sea assets on a shared tactical map. That's a $20,000 demo.