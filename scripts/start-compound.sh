#!/bin/bash
# Start C2 services configured for the compound challenge (single Iris drone, multicast).
# Usage: bash scripts/start-compound.sh
#
# Gazebo + SITL must be launched separately:
#   Terminal 1: ./launch_gz.sh
#   Terminal 2: ./launch_sitl.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Compound-specific environment ──
export BATTLESPACE_WAYPOINTS="$PROJECT_ROOT/data/compound/waypoints.json"
export BATTLESPACE_FLEET="$PROJECT_ROOT/data/compound/fleet.json"
export BATTLESPACE_NO_GO_ZONES="$PROJECT_ROOT/data/compound/no_go_zones.json"

# Find python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Cannot find python."
    exit 1
fi

echo "=== C2 Compound Challenge Mode ==="
echo "Python: $($PYTHON --version 2>&1)"
echo "Fleet:     $BATTLESPACE_FLEET"
echo "Waypoints: $BATTLESPACE_WAYPOINTS"
echo "No-go:     $BATTLESPACE_NO_GO_ZONES"
echo ""

# ---- Kill old processes on our ports ----
echo "Clearing ports..."
for port in 8000 8001 8002 8003 8004 8005; do
    lsof -ti :$port 2>/dev/null | xargs kill -9 2>/dev/null || true
done
sleep 1

# ---- Helper: wait for a port to respond ----
wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=$3
    local elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        if curl -s --max-time 1 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
            echo "  OK   $name (:$port)"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    echo "  WAIT $name (:$port) — still starting"
    return 1
}

# ---- Start services ----
ALL_PIDS=""
echo "Starting services..."
echo ""

# 1. WebSocket Hub
$PYTHON -m uvicorn src.websocket_hub.server:app --host 0.0.0.0 --port 8005 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8005 "WebSocket Hub" 5

# 2. Coordinator (with no-go zone validation)
$PYTHON -m uvicorn src.coordinator.server:app --host 0.0.0.0 --port 8000 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8000 "Coordinator" 5

# 3. NLU Parser
$PYTHON -m uvicorn src.nlu.server:app --host 0.0.0.0 --port 8002 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8002 "NLU Parser" 5

# 4. IFF Engine
$PYTHON -m uvicorn src.iff.server:app --host 0.0.0.0 --port 8004 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8004 "IFF Engine" 5

# 5. Vehicle Bridge (connects via multicast to SITL)
$PYTHON -m uvicorn src.vehicles.server:app --host 0.0.0.0 --port 8003 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8003 "Vehicle Bridge" 20

# 6. Voice ASR
$PYTHON -m uvicorn src.voice.server:app --host 0.0.0.0 --port 8001 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8001 "Voice ASR" 30

# ---- Dashboard ----
echo ""
echo "Starting dashboard..."
cd "$PROJECT_ROOT/src/dashboard" && npm run dev &
ALL_PIDS="$ALL_PIDS $!"
cd "$PROJECT_ROOT"

# ---- Final summary ----
echo ""
echo "=== Services Ready ==="
PASS=0
for entry in "8005:WebSocket Hub" "8000:Coordinator" "8002:NLU Parser" "8003:Vehicle Bridge" "8004:IFF Engine" "8001:Voice ASR"; do
    port="${entry%%:*}"
    name="${entry#*:}"
    if curl -s --max-time 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
        PASS=$((PASS + 1))
    fi
done
echo "$PASS/6 backend services running."
echo ""
echo "=== Next Steps ==="
echo "1. In another terminal: ./launch_gz.sh       (start Gazebo world)"
echo "2. In another terminal: ./launch_sitl.sh      (start ArduPilot SITL)"
echo "3. Open dashboard at http://localhost:3000"
echo "4. Issue voice commands or use scripts/test-practice-commands.py"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# ---- Ctrl+C handler ----
cleanup() {
    echo ""
    echo "Stopping..."
    for p in $ALL_PIDS; do
        kill "$p" 2>/dev/null || true
    done
    sleep 1
    for port in 8000 8001 8002 8003 8004 8005; do
        lsof -ti :$port 2>/dev/null | xargs kill -9 2>/dev/null || true
    done
    echo "All services stopped."
    exit 0
}
trap cleanup INT TERM

wait
