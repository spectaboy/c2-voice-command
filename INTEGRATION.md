# Integration Guide — What To Do After All Agents Finish

## Step 1 — Audit First (No Code Yet)

Paste this into the Coordinator terminal:

```
Read CLAUDE.md. Do NOT write any code yet.

Audit the entire codebase across all src/ folders and tell me:
1. Does every service have a /health endpoint?
2. Are all imports consistent — does any service import something that doesn't exist?
3. Do the Pydantic schemas in src/shared/schemas.py match what each service actually sends/receives?
4. Is the WebSocket hub in src/coordinator/ wired up correctly?
5. List every hardcoded port and confirm it matches src/shared/constants.py
6. What is the exact order I need to start services so nothing crashes on startup?

Give me a report. Do not fix anything yet — just tell me what's broken.
```

Wait for the report. Fix all blockers before running anything.

---

## Step 2 — Start Everything In This Exact Order

```bash
# 1. FreeTAKServer (must be first)
docker compose up -d

# 2. Start all 6 SITL instances
./scripts/start-sitl.sh

# 3. Wait 10 seconds, then start services
python -m src.vehicles.server    # Vehicle bridge  :8003
python -m src.tak.server         # TAK/IFF         :8004
python -m src.coordinator.server # Coordinator + WS :8000 :8005
python -m src.nlu.server         # NLU              :8002
python -m src.voice.server       # Voice ASR        :8001

# 4. Dashboard last
cd src/dashboard && npm run dev  # :3000
```

---

## Step 3 — Smoke Test Every Service

```bash
# Health checks — all must return 200
curl localhost:8001/health
curl localhost:8002/health
curl localhost:8000/health
curl localhost:8003/health
curl localhost:8004/health

# Test NLU parsing
curl -X POST localhost:8002/parse \
  -H "Content-Type: application/json" \
  -d '{"transcript": "UAV-1 move to patrol position"}'

# Test a vehicle command end-to-end
curl -X POST localhost:8000/command \
  -H "Content-Type: application/json" \
  -d '{
    "command_type": "move",
    "vehicle_callsign": "UAV-1",
    "domain": "air",
    "location": {"lat": 38.91, "lon": -77.03, "alt_m": 100}
  }'

# Verify in FreeTAKServer web UI → localhost:5000
# UAV-1 should appear/move on the map
```

---

## Step 4 — If Something Is Broken

Paste this into the relevant agent terminal:

```
Service [X] is failing with this error: [paste full error here]

Read the relevant source files, find the root cause, fix it.
Update tasks/lessons.md with what was wrong and how you fixed it.
```

> Fix one error at a time. Do not fix multiple services simultaneously.

---

## Step 5 — Full Voice Pipeline Test

Once all health checks pass:

1. Press **spacebar** (push-to-talk)
2. Say **"UAV-1, move to overwatch position"**
3. Verify the chain:
   - [ ] Terminal shows Whisper transcript
   - [ ] Dashboard shows parsed command in transcript log
   - [ ] ATAK map shows UAV-1 icon moving
   - [ ] Dashboard Leaflet map marker moves
   - [ ] Vehicle status card updates speed/heading

If all 5 boxes check — integration is done. Move to demo rehearsal.

---

## Golden Rule

> **Do not add features. Do not refactor. Make what exists connect.**
> You are in integration mode, not build mode.
> One error at a time. Prove it works before moving on.
