# Voice-driven UxS - Applicant Guide
## Voice-Driven Command & Control for Uncrewed Systems

### Overview

In modern operations, the ability to command uncrewed systems quickly and naturally is a force multiplier. What if an operator could simply speak to control drones — and the system would understand, validate, and execute?

Your task: build a voice-driven command and control (C2) system that translates natural speech into drone commands, enforces safety rules, and gives the operator clear feedback. You will work with simulated drones in a 3D environment, a pre-defined battlespace with waypoints and entities, and an automated scoring system that tests your system's accuracy and robustness.

**Event Date:** Saturday, March 21, 2026
**Location:** SAIT, Calgary
**Event Time:** 8:30 AM - 8:00 PM
**Team Size:** Up to 5

---

### The Scenario

You are an operator at a forward operating base. You have a few drones on the pad and a battlespace with designated waypoints and known contacts — some friendly, some unknown, some hostile. Your sensor feeds and intelligence reports are available as structured data files.

Your job is to build a system where you speak commands — "Take off to 20 meters", "Fly to Waypoint Bravo", "Investigate the unknown contact" — and the drones respond. But it's not just about moving drones around. Your system must be smart: it should refuse to engage friendly forces, warn you about unknowns, confirm high-risk actions, and handle the messy reality of natural speech.

The core question: can your system turn voice into controlled, safe action?

---

### What You're Building

Your system connects three layers: a voice pipeline that turns speech into text, a command engine that parses and validates those commands, and a drone interface that executes them in simulation.

**Core System (Required)**

**1. Voice-to-Text Pipeline**
Capture spoken commands and convert them to text using any speech-to-text engine. OpenAI Whisper (runs locally, no API key needed), Google Speech API, or the browser's built-in Web Speech API all work. The choice is yours.

**2. Command Parser & Safety Engine**
This is the intellectual core of the challenge. Parse natural language into structured drone commands. Validate them against safety rules: check the battlespace entity list before allowing engagement actions, require confirmation for high-risk commands, and block actions that target friendly forces.

**3. Drone Control Interface**
Send validated commands to simulated drones via MAVSDK-Python or similar. Your drones run in ArduPilot SITL (Software-In-The-Loop) — a full flight controller simulation. You'll see them fly in a 3D Gazebo environment rendered in your browser.

**4. Operator Feedback**
Show the operator what's happening. At minimum: a command log (what was spoken, what was parsed, what was executed), drone telemetry (position, altitude, battery, mode), and clear confirmation prompts for high-risk actions. This can be a terminal, a web dashboard, or anything visual.

---

### Suggested Architecture

```
Voice Input --> Speech-to-Text Engine
                       |
                       v
            Command Parser & Validator
             (parse, check IFF, safety)
                    |          |
                    v          v
            MAVSDK-Python   Operator UI
            (drone control) (feedback display)
                    |
                    v
          ArduPilot SITL + Gazebo
          (simulated drones in 3D)
```

---

### The Battlespace

**Waypoints** — Named locations in the area of operations (Alpha through Hotel). Each has GPS coordinates. Commands like "fly to Waypoint Bravo" should resolve to the correct location.

**Entity List (IFF)** — A JSON file containing known contacts in the battlespace, each classified as FRIENDLY, UNKNOWN, or HOSTILE. Your system must check this list before executing engagement-related commands:

- Commands targeting friendly entities → Block with a clear warning
- Commands targeting unknown entities → Require confirmation before proceeding
- Commands targeting hostile entities → Allow, but still confirm high-risk actions like "engage"

**Drone Configuration** — Two drones are available: "Alpha" and "Bravo". Each runs as a separate SITL instance on a known port.

These files will be available for download on the day of the event.

---

### How You'll Be Evaluated

**Technical Score** — Your system will be evaluated on how well it handles a range of commands, from basic single-drone control to more complex scenarios involving multiple drones, IFF safety logic, and edge cases. Expect your system to be tested on things like:

- Basic drone commands (takeoff, navigation, landing)
- Compound and parameterized commands
- IFF awareness and safety rule enforcement
- Multi-drone coordination
- Graceful handling of ambiguous, contradictory, or invalid input

**Demos** — Each team gets a short presentation slot to demo their system live and explain their design decisions. This is your chance to show off voice integration, UX polish, and creative features.

A practice dataset will be provided at the start of the hackathon so you can test your system during development. The final evaluation may use a different set of scenarios.

---

### Technical Details

**What You'll Receive on the Day**
- Cloud simulation environment — A GPU-accelerated VM per team running Gazebo (3D visualization) + ArduPilot SITL (drone physics). Access via browser. Your code will control the SITL systems over the internet.
- Starter code — Connection examples, waypoint coordinates, battlespace entity file, and a practice dataset for self-testing during development
- This guide and the full challenge brief with evaluation criteria

**Recommended Tools**

| Component | Recommended | Alternatives |
|-----------|-------------|--------------|
| Speech-to-Text | OpenAI Whisper (local) | Google Speech API, Web Speech API |
| Command Parsing | Python + regex or LLM | SpaCy, custom grammar |
| Drone API | MAVSDK-Python | pymavlink (lower-level) |
| UI Framework | Streamlit, Flask, terminal | React, PyQt, Tkinter |
| Map Display | Folium, Leaflet.js | Google Maps API |

**Technical Constraints**
- Software only. No hardware is involved. Everything runs in simulation.
- Language agnostic. Python is recommended but not required.
- Bring your own laptop. You'll need a modern laptop with Python 3.10+ and a browser.

---

### Glossary

| Term | Definition |
|------|------------|
| UxS | Uncrewed Systems -- drones, rovers, and other unmanned platforms |
| C2 | Command and Control -- the system and process for directing operations |
| SITL | Software-In-The-Loop -- a full flight controller simulation that runs on a PC |
| MAVSDK | The Python SDK for communicating with MAVLink-based drones and rovers |
| Gazebo | A 3D robotics simulator used to visualize drone flight |
| IFF | Identification Friend or Foe -- classifying contacts in the battlespace |
| RTL | Return to Launch -- a standard command for the drone to fly home and land |
| STT | Speech-to-Text -- converting spoken audio into written text |
| Waypoint | A named GPS coordinate in the area of operations |
| noVNC | A browser-based VNC client for accessing remote desktops |

---

### Timeline

| Time | Activity |
|------|----------|
| Pre-event | Applicant Guide Released (this document) |
| 8:30 AM - 9:10 AM | Participant Check-In and Breakfast |
| 9:15 AM - 9:45 AM | Kickoff & Challenge Reveal |
| 9:50 AM - 12:15 PM | Hacking Session #1 |
| 12:15 PM - 1:00 PM | Lunch + Reset |
| 1:00 PM - 4:00 PM | Hacking Session #2 |
| 4:00 PM - 4:30 PM | Final Submissions & Pitch Order Draw |
| 4:30 PM - 4:45 PM | Break/Guest Arrival & Appetizers |
| 4:45 PM - 5:00 PM | Opening Remarks and Introduction of Judges |
| 5:00 PM - 6:45 PM | Final Presentations |
| 7:10 PM - 8:00 PM | Awards & Close |

Times are approximate and may shift. Final schedule will be confirmed closer to the event.
