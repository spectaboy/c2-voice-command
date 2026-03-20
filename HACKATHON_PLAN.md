# Hackathon Game Plan — CalgaryHacks March 21, 2026

## Status: End-to-End Pipeline WORKING
- Voice → Whisper → Claude NLU → Coordinator → Vehicle Bridge → Mock SITL → Dashboard ✅
- 6 mock vehicles on map, armed, moving in GUIDED mode ✅
- Voice transcripts showing in dashboard ✅
- Vehicle status cards updating in real-time ✅
- Slow but functional (~10-15s voice-to-action latency)

---

## What The Hackathon Gives Us (on March 21)

| Item | Details |
|------|---------|
| **Cloud VM** | GPU VM per team with Gazebo + ArduPilot SITL, browser access via noVNC |
| **Drones** | 2 drones: "Alpha" and "Bravo" on separate SITL ports |
| **Waypoints** | Alpha through Hotel — GPS coordinates in a file |
| **Entity List** | JSON file: contacts classified FRIENDLY / UNKNOWN / HOSTILE |
| **Starter Code** | Connection examples, practice dataset |
| **Hacking Time** | 9:50 AM - 4:00 PM (~6 hours) |

---

## What We Have vs What They Need

| Hackathon Requirement | Our Implementation | Status | Gap |
|---|---|---|---|
| Voice-to-Text | Whisper (faster-whisper large-v3-turbo) | ✅ Working | Slow on CPU (~10s) |
| Command Parser + Safety | Claude API tool-calling + IFF engine | ✅ Working | Need to load THEIR entity file |
-focus heavily on our voice command and control system and make it as robust as possible, smart, efficeint... because this is what the hackathon is about. they giving the simulation and the drones, we just need to make the voice command and control system. but it has to be perfect.... we using the industry standard tools and libraries as well as research papers to make it as good as possible, and the logic... the logic has to be perfect....
| Drone Control | pymavlink to ArduPilot SITL | ✅ Working | They recommend MAVSDK-Python but pymavlink is valid |
| Operator Feedback | Full React dashboard + Leaflet map| ✅ Way beyond others | Polish |
| 2 drones | We have 6 vehicles | ✅ Overkill | Make fleet configurable |
| Waypoint navigation | Hardcoded Halifax locations | ⚠️ Partial | Need to load THEIR waypoint file |
| IFF safety enforcement | IFF engine exists | ⚠️ Untested | Wire up entity file → block friendly, confirm unknown |
| Takeoff/Land commands | NLU tools exist | ⚠️ Partial | Add explicit takeoff/land tools |
| Confirmation flow | Coordinator + TTS readback | ⚠️ Untested | Test end-to-end |
| Edge cases | Claude handles naturally | ⚠️ Untested | Test ambiguous/invalid input |

---

## Priority Tasks (March 18-20)

### P0 — Must Have (blocks everything)

#### 1. Configurable Fleet + Waypoints
- [x] Load vehicle config from `battlespace.json` instead of hardcoded `constants.py`
- [x] Load waypoint file and inject into NLU system prompt
- [x] Load entity file into IFF engine
- [x] Support 2-drone config (Alpha/Bravo) alongside our 6-vehicle config
- [x] Connection address configurable (localhost vs cloud VM IP)

#### 2. Add Missing Commands
- [x] `takeoff` tool — "Take off to 20 meters" (NLU + vehicle bridge)
- [x] `land` tool — "Land Alpha" (NLU + vehicle bridge)
- [x] `arm`/`disarm` if needed by scoring
- [x] Compound commands — "Take off and fly to Bravo" = takeoff then move

#### 3. IFF Safety Enforcement (Scoring Critical)
- [x] On ENGAGE command: check entity list
- [x] FRIENDLY target → BLOCK, return warning message
- [x] UNKNOWN target → require confirmation before executing
- [x] HOSTILE target → allow but confirm high-risk
- [x] Dashboard shows IFF blocking/warning in transcript log

#### 4. Voice → Command → Execute Full Loop Verification
- [ ] Test: "Alpha take off to 20 meters" → drone takes off
- [ ] Test: "Fly to Waypoint Bravo" → drone moves to coordinates
- [ ] Test: "Alpha and Bravo fly to Charlie" → both move
- [ ] Test: "Land Alpha" → drone lands
- [ ] Test: "Engage the friendly" → BLOCKED
- [ ] Test: "Investigate unknown contact" → confirmation required
- [ ] Test: gibberish → graceful error

### P1 — Should Have (differentiators)

#### 5. Latency Optimization
- [x] Pre-load Whisper model (already done on startup)
- [x] Model configurable via WHISPER_MODEL env var (large-v3-turbo for GPU, small for CPU)
- [x] Use `claude-haiku-4-5` for NLU instead of Sonnet (faster, cheaper)
- [x] Transcript appears on dashboard IMMEDIATELY while NLU processes

#### 6. Gazebo Visual Testing
- [ ] Skip pre-event — they provide VMs with Gazebo on hackathon day
- [ ] Test with mock SITL locally (already works)

#### 7. Dashboard Polish
- [x] Show command parsing result in transcript log (not just raw text)
- [x] Show error messages when commands fail (red, color-coded)
- [x] Show IFF blocks in transcript (red X with reason)
- [x] Show execution confirmations (green checkmark with readback)
- [x] Show confirmation requests (yellow with readback text)
- [x] Suppress CoTSender spam (FTS is optional)
- [x] Connection status for vehicle bridge (header bar)
- [x] Map centered on Halifax (was Ottawa)
- [x] CORS on coordinator for dashboard confirmations
- [x] Fixed confirmation modal POST URL (coordinator:8000)

### P2 — Nice to Have (wow factor)

#### 8. TTS Voice Feedback
- [x] Readback: "UAV-1 proceeding to target location" spoken aloud on execution
- [x] Confirmation: "CONFIRM: CRITICAL RISK..." readback via TTS
- [x] Error: "BLOCKED: target is FRIENDLY" spoken via TTS
- [x] Confirmed/Cancelled: "Confirmed. Executing." / "Cancelled." via TTS
- [x] Radio-style beep + effects on all TTS

#### 9. Advanced Commands
- [x] "Set up a perimeter patrol between Alpha and Bravo" (patrol_route tool)
- [x] "What's the status of all drones?" (request_status tool)
- [x] "Abort all missions, RTB everyone" (return_to_base with abort language)

#### 10. Demo Rehearsal
- [x] Demo script written (see below)
- [ ] Practice transitions between commands
- [ ] Have backup commands ready if voice recognition fails
- [ ] Prepare slides (2-3 max) explaining architecture

---

## Gazebo Setup (For Visual Testing)

### Option A: Quick Visual Check — QGroundControl (5 min)
Download QGroundControl on Windows. Connect to SITL on UDP 14550. See flight instruments + map.

### Option B: Gazebo in WSL2 via WSLg (30-60 min)
```bash
# In WSL2 Ubuntu:

# 1. Install Gazebo Harmonic
sudo apt update
sudo apt install -y lsb-release wget gnupg
sudo wget https://packages.osrfoundation.org/gazebo.gpg \
  -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
  http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
sudo apt update
sudo apt install -y gz-harmonic

# 2. Build ardupilot_gazebo plugin
sudo apt install -y libgz-sim8-dev rapidjson-dev
mkdir -p ~/gz_ws/src && cd ~/gz_ws/src
git clone https://github.com/ArduPilot/ardupilot_gazebo
cd ardupilot_gazebo && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j4

# 3. Set environment
echo 'export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/gz_ws/src/ardupilot_gazebo/build' >> ~/.bashrc
echo 'export GZ_SIM_RESOURCE_PATH=$HOME/gz_ws/src/ardupilot_gazebo/models:$HOME/gz_ws/src/ardupilot_gazebo/worlds' >> ~/.bashrc
source ~/.bashrc

# 4. Launch Gazebo (Terminal 1)
gz sim -v4 -r iris_runway.sdf

# 5. Launch SITL connected to Gazebo (Terminal 2)
cd ~/ardupilot
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console

# 6. In MAVProxy console, fly it:
#    mode guided
#    arm throttle
#    takeoff 20
```

WSLg should render Gazebo directly on your Windows desktop. If you get a black screen:
```bash
export LIBGL_ALWAYS_SOFTWARE=1  # CPU rendering fallback
```

### Option C: Hackathon Day (No Setup Needed)
They provide cloud VMs. Open browser → noVNC → see Gazebo. Point our code at their SITL IP/ports.

---

## Hackathon Day Adaptation Checklist

When we arrive and get the cloud VM + starter files:

1. **Read their waypoint file** → Update `constants.py` or load dynamically
2. **Read their entity JSON** → Feed into IFF engine
3. **Get SITL connection details** → Update vehicle bridge connection strings
4. **Test basic commands** against their SITL:
   - Takeoff → Does the drone fly in Gazebo?
   - Move to waypoint → Does it navigate?
   - Land → Does it come down?
5. **Run the practice dataset** they provide
6. **Fine-tune** any issues discovered

### Quick Adaptation Code (prep this before event):
```python
# src/shared/battlespace_loader.py
import json

def load_waypoints(filepath: str) -> dict:
    """Load waypoint file → {name: {lat, lon, alt}}"""
    with open(filepath) as f:
        return json.load(f)

def load_entities(filepath: str) -> list:
    """Load entity file → [{uid, name, affiliation, lat, lon}]"""
    with open(filepath) as f:
        return json.load(f)

def load_fleet(filepath: str) -> dict:
    """Load drone config → {callsign: {port, sysid, type}}"""
    with open(filepath) as f:
        return json.load(f)
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OPERATOR (Browser)                           │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │ Push-to- │  │ Tactical Map │  │  Vehicle   │  │  Transcript  │ │
│  │  Talk    │  │  (Leaflet)   │  │  Status    │  │    Log       │ │
│  └────┬─────┘  └──────────────┘  └────────────┘  └──────────────┘ │
│       │              ▲                  ▲                ▲          │
└───────┼──────────────┼──────────────────┼────────────────┼──────────┘
        │              │ WebSocket :8005  │                │
        │ audio        └─────────┬────────┘                │
        │                        │                         │
   ┌────▼─────┐          ┌──────┴──────┐                   │
   │ Voice ASR│          │  WebSocket  │◄──────────────────┘
   │  :8001   │          │   Hub :8005 │
   │ (Whisper)│          └──────▲──────┘
   └────┬─────┘                 │ broadcast
        │ transcript            │
   ┌────▼─────┐          ┌─────┴───────┐       ┌──────────────┐
   │   NLU    │          │ Coordinator │──────►│ Vehicle Bridge│
   │  :8002   ├─────────►│   :8000     │       │    :8003      │
   │ (Claude) │ commands │ (risk/confirm)       │  (pymavlink)  │
   └──────────┘          └──────┬──────┘       └──────┬────────┘
                                │                      │ MAVLink TCP
                         ┌──────▼──────┐        ┌──────▼────────┐
                         │ IFF Engine  │        │  ArduPilot    │
                         │   :8004     │        │  SITL/Gazebo  │
                         │ (safety)    │        │  :5760, :5770 │
                         └─────────────┘        └───────────────┘
```

---

## Demo Script (5 minutes)

### Opening (30s)
"We built a voice-driven command and control system. Speak naturally, and drones respond safely."

### Demo 1: Basic Commands (90s)
- "Alpha, take off to 20 meters" → drone rises in Gazebo
- "Fly to Waypoint Bravo" → drone navigates
- "Alpha, land" → drone lands

### Demo 2: Multi-Drone (60s)
- "Alpha and Bravo, fly to Waypoint Charlie" → both move
- Point out real-time telemetry on dashboard

### Demo 3: IFF Safety (90s)
- "Engage the friendly patrol" → BLOCKED, system warns
- "Investigate the unknown contact" → confirmation required → "Confirm" → executes
- "Engage the hostile target" → high-risk confirmation → "Confirm" → executes

### Demo 4: Edge Cases (30s)
- Say something ambiguous → system asks for clarification
- Say gibberish → graceful error

### Close (30s)
"Natural speech to safe, validated drone action. Our architecture scales from 2 drones to full fleet ops."

---

## Key Files to Modify

| File | What to Change |
|------|---------------|
| `src/shared/constants.py` | Make VEHICLES configurable, add waypoints |
| `src/nlu/parser.py` | System prompt: inject loaded waypoints |
| `src/nlu/tools.py` | Add `takeoff`, `land` tools |
| `src/vehicles/mavlink_client.py` | Add `land()` method |
| `src/vehicles/vehicle_manager.py` | Handle TAKEOFF, LAND command types |
| `src/coordinator/risk.py` | IFF entity check on ENGAGE |
| `src/shared/schemas.py` | Add TAKEOFF, LAND to CommandType enum |
| `src/voice/server.py` | Already fixed (forwards commands to coordinator) |
| `scripts/start_all.py` | Already includes mock SITL |

---

## Competitive Edge

What sets us apart from other teams who will have 6 hours to build from scratch:

1. **Full React dashboard** — others will have terminal output or Streamlit
2. **Claude tool-calling NLU** — others will use regex or basic NLP
3. **Real-time tactical map** — others won't have this
4. **Military symbology** — domain-specific vehicle markers
5. **IFF engine with audit trail** — others will have basic if/else
6. **Multi-vehicle architecture** — we support 6, they need 2
7. **Voice confirmation flow** — TTS readback + voice confirm
8. **Pre-built, tested** — we just plug into their environment

We are bringing a polished product while others start from scratch. The 6 hours of hacking time is for us to adapt and polish, not build.
