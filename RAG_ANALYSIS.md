# RAG Pipeline Analysis: Voice-Controlled Drone C2 System

**Author:** Senior Engineering Analysis
**Date:** March 20, 2026
**Context:** CalgaryHacks hackathon prep — should we add RAG to fix complex command handling?

---

## The Problem

The system only handles simple single-action commands reliably. When the operator says compound things like "Alpha take off, fly to Bravo, then investigate the unknown contact near Delta," it either:
- Only executes the first action
- Fires all actions simultaneously (move executes before takeoff finishes)
- Fails to understand spatial/contextual intent

## What RAG Would Actually Mean Here

### What would be retrieved?

| Data Category | Size | Already in Prompt? | RAG Useful? |
|---|---|---|---|
| ArduPilot docs/command reference | Large | No | **No** — Claude picks from 10 fixed tools, doesn't invent MAVLink commands |
| Command pattern examples (few-shot) | Medium | Partially (via context.py corrections) | **Marginal** — only edge case phrasings benefit |
| Vehicle state/telemetry | Tiny (2 drones) | No | **No** — just put it in the prompt directly |
| Battlespace context (waypoints, entities) | Small (8 waypoints, 6 entities) | Yes, already there | **No** — already fits in ~600 tokens |

### The Pipeline

```
Voice → Whisper → [embed transcript → vector search → retrieve context] → Claude API → Coordinator
```

### How does this differ from just putting more context in the system prompt?

**It doesn't meaningfully differ.** The entire knowledge base is ~1,200 tokens. Claude Haiku's context window is 200K tokens. We're using less than 1% of it. RAG is useful when you have more context than fits in the prompt, or when the relevant subset varies per query. **We have neither problem.**

---

## RAG Pros (being fair)

1. **ArduPilot edge case knowledge** — If operator says "set position hold mode," retrieving a doc chunk about POSHOLD could help. But our 10 fixed tools already constrain what Claude can do.

2. **Few-shot example retrieval** — "Have the bird do a circuit around charlie" could retrieve similar examples mapping to `loiter_at` or `patrol_route`. This is the only genuinely useful RAG application.

3. **Scalability** — If we had 500 waypoints, 200 entities, 50 vehicles, the prompt would overflow and retrieval would help focus. But we have 8 waypoints, 6 entities, 2 drones.

---

## RAG Cons

### 1. Latency Impact (dealbreaker)

Current pipeline timing:
| Step | Time |
|---|---|
| Whisper (GPU) | ~1-2s |
| Claude Haiku API | ~0.5-1s |
| Coordinator + MAVLink | ~0.1-0.3s |
| **Total** | **~2-3s** |

Adding RAG:
| Step | Added Time |
|---|---|
| Embed transcript | +50-500ms |
| Vector search | +10-50ms |
| **New total** | **~2.5-3.5s** |

We're already at the edge of sub-3s. Adding RAG risks blowing the latency budget for marginal benefit.

### 2. Complexity (2-3 hours of hackathon time)

Setup requires: vector DB (chromadb), embedding model, document chunking, indexing pipeline, retrieval pipeline, prompt integration, failure handling. That's 30-50% of hackathon time on infrastructure that doesn't solve the core problem.

### 3. Over-engineering Risk

Judges will ask "why RAG?" and the honest answer is "edge case phrasings." That's not compelling. They'll be more impressed by a system that reliably executes 10 command types than one with a RAG pipeline that fumbles basic takeoff.

### 4. RAG Does NOT Solve the Actual Problem

**The system's failures are NOT knowledge retrieval failures.** They are:

| Actual Problem | RAG Fixes It? |
|---|---|
| Claude doesn't know current vehicle position/altitude | **No** — RAG retrieves static docs, not live telemetry |
| Compound commands fire without waiting for completion | **No** — this is execution sequencing, not parsing |
| No feedback between sequential commands | **No** — this is architecture, not knowledge |
| Can't reason spatially ("go north", "move closer") | **No** — needs live state, not document retrieval |
| "Investigate area" has no tool mapping | **No** — needs macro commands, not more context |

---

## What Actually Fixes the Problem (Alternatives)

### Alternative A: Agentic Loop (Multi-Turn Tool Use)

Claude calls tool → sees result → decides next action → calls next tool → repeat.

**Fixes:** Everything. Compound commands, feedback, state awareness.
**Kills:** Latency. Each loop = 0.5-1s API call. 3-step command = 3-5s of API alone.
**Hackathon viable?** No. Too slow, too risky, too complex for 6 hours.

### Alternative B: Live State Injection (**RECOMMENDED**)

Before calling Claude, fetch current telemetry and inject into system prompt:
```
## Current Vehicle State
- Alpha: GUIDED mode, armed, at (44.6488, -63.5752, 20.0m), heading 90, speed 5.2 m/s
- Bravo: STABILIZE mode, disarmed, at (44.6520, -63.5700, 0.0m), on ground
```

**Fixes:** Spatial reasoning, relative commands ("go higher", "move north", "fly closer to Bravo"), state-aware parsing (don't takeoff if already airborne).
**Cost:** ~5-20ms latency (one HTTP GET to localhost). 30-60 min to implement.
**Hackathon viable?** Absolutely. Highest value per hour spent.

### Alternative C: Command Sequencer (**RECOMMENDED**)

Add delay-based sequencing between compound commands:
```python
for i, cmd in enumerate(commands):
    if i > 0 and commands[i-1]["command_type"] == "takeoff":
        await asyncio.sleep(5)  # Wait for takeoff to complete
    await client.post("http://localhost:8000/command", json=cmd)
```

**Fixes:** Compound commands ("take off and fly to Bravo" actually works).
**Cost:** Zero latency for single commands. 5s delay only after takeoff.
**Hackathon viable?** 20 lines of code. 30 min to implement and test.

### Alternative D: Expanded Tool Set

Add `get_vehicle_position`, `wait_for_completion` tools. Only useful with an agentic loop (Alt A). Claude can't use the result in a single-turn parse.

**Hackathon viable?** No. Requires Alt A which is too slow.

### Alternative E: Macro Commands (**RECOMMENDED**)

Pre-built templates that expand into sequenced primitives:

| Macro | Expands To |
|---|---|
| `investigate_contact(Alpha, hostile-vehicle-1)` | takeoff (if needed) → fly to contact position → loiter 60s |
| `search_area(Bravo, waypoint_Charlie)` | takeoff (if needed) → fly to waypoint → orbit at 50m |
| `escort_to(Alpha, Bravo, waypoint_Delta)` | fly both to waypoint in formation |

Claude calls ONE tool. The coordinator handles sequencing internally.

**Fixes:** Complex commands become single tool calls. Reliable, testable sequences.
**Cost:** 1-2 hours for 2-3 macros.
**Hackathon viable?** Yes, after Alternatives B and C are done.

---

## Recommendation

### Do NOT build RAG.

RAG is the wrong tool for this problem. You don't have a knowledge retrieval problem. You have:
1. **A state awareness problem** → Fix with live state injection (Alt B)
2. **A command sequencing problem** → Fix with command sequencer (Alt C)
3. **A command abstraction problem** → Fix with macro commands (Alt E)

### Build Priority (hackathon 6-hour plan)

| Hour | Task | Alternative | Impact |
|---|---|---|---|
| 0-1 | **Live State Injection** — fetch telemetry, inject into NLU prompt | B | Enables spatial reasoning, relative commands |
| 1-2 | **Command Sequencer** — delay between takeoff/move in compound commands | C | Fixes "take off and fly to X" |
| 2-3 | **End-to-end testing** — run all demo commands, fix bugs | — | Reliability |
| 3-4 | **1-2 Macro Commands** — `investigate_contact`, `search_area` | E | Scores "compound commands" |
| 4-5 | **Edge cases + polish** — ambiguous input, corrections, TTS | — | Scores "edge cases" |
| 5-6 | **Demo rehearsal** — practice the 5-min demo | — | Presentation score |

### The Meta-Lesson

At a hackathon, winning systems aren't the most architecturally sophisticated. They're the ones that work reliably during the live demo. A system that correctly handles 10 basic commands with clear voice feedback scores higher than one with a RAG pipeline and an agentic loop that crashes during the demo.

Your existing architecture is strong:
- Claude tool-calling for NLU is already better than 90% of teams
- IFF engine with engagement blocking is a genuine differentiator
- React dashboard with Leaflet map is polished
- TTS readback creates a complete voice-in/voice-out loop

Focus your 6 hours on making the core loop bulletproof: **voice in → correct parse → correct execution → clear feedback.**

RAG is a solution looking for a problem you don't have.

---

## Implementation Details

### Files to Modify

| File | Change | Time |
|---|---|---|
| `src/nlu/parser.py` | Add telemetry fetch before Claude API call, inject vehicle state into system prompt | 45 min |
| `src/voice/server.py` | Add delay-based sequencing in `_emit_transcript` command loop | 30 min |
| `src/nlu/tools.py` | Add `investigate_contact` and `search_area` macro tool definitions | 30 min |
| `src/coordinator/server.py` | Add macro expansion in `handle_command` — decompose macros into sequenced primitives | 45 min |
| `src/vehicles/vehicle_manager.py` | Add `get_position(callsign)` helper for quick state queries | 15 min |

### Verification

Test these commands after implementation:
1. "Alpha take off to 20 meters" → drone lifts off (basic)
2. "Alpha take off and fly to Bravo" → takeoff, wait, then move (compound + sequencer)
3. "Move Alpha 500 meters north" → calculates from current position (live state)
4. "Investigate the unknown contact" → macro expands to fly + loiter (macro)
5. "Engage the friendly patrol" → BLOCKED (IFF safety)
6. "Engage the hostile vehicle" → confirmation required (IFF + confirm)
7. Gibberish → graceful error (edge case)
