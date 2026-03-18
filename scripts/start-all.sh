#!/bin/bash
# Start all C2 services. Run from project root.
# Usage: bash scripts/start-all.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Find python
PYTHON=""
for cmd in python python.exe python3 /c/Python314/python.exe; do
    if command -v "$cmd" &>/dev/null || [ -f "$cmd" ]; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Cannot find python."
    exit 1
fi

echo "=== C2 Voice Command System ==="
echo "Python: $($PYTHON --version 2>&1)"
echo ""

# ---- Kill old processes ----
echo "Clearing ports..."
for port in 8000 8001 8002 8003 8004 8005; do
    for _ in 1 2; do
        pid=$(netstat -ano 2>/dev/null | grep "0.0.0.0:${port}" | grep "LISTEN" | awk '{print $NF}' | head -1)
        if [ -n "$pid" ] && [ "$pid" != "0" ]; then
            taskkill //F //PID "$pid" >/dev/null 2>&1 || true
        fi
    done
done
sleep 2

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

# ---- Start services one by one and verify ----
ALL_PIDS=""

echo "Starting services..."
echo ""

# 1. WebSocket Hub (fast, no deps)
$PYTHON -m uvicorn src.websocket_hub.server:app --host 0.0.0.0 --port 8005 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8005 "WebSocket Hub" 5

# 2. Coordinator (fast, no deps)
$PYTHON -m uvicorn src.coordinator.server:app --host 0.0.0.0 --port 8000 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8000 "Coordinator" 5

# 3. NLU Parser (needs API key, fast start)
$PYTHON -m uvicorn src.nlu.server:app --host 0.0.0.0 --port 8002 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8002 "NLU Parser" 5

# 4. IFF Engine (tries FTS connection, fast otherwise)
$PYTHON -m uvicorn src.iff.server:app --host 0.0.0.0 --port 8004 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8004 "IFF Engine" 5

# 5. Vehicle Bridge (tries SITL connections — takes ~10s to timeout)
$PYTHON -m uvicorn src.vehicles.server:app --host 0.0.0.0 --port 8003 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8003 "Vehicle Bridge" 20

# 6. Voice ASR (loads Whisper model — takes ~5-10s)
$PYTHON -m uvicorn src.voice.server:app --host 0.0.0.0 --port 8001 --log-level warning &
ALL_PIDS="$ALL_PIDS $!"
wait_for_port 8001 "Voice ASR" 30

# ---- Final summary ----
echo ""
echo "=== Final Status ==="
PASS=0
for entry in "8005:WebSocket Hub" "8000:Coordinator" "8002:NLU Parser" "8003:Vehicle Bridge" "8004:IFF Engine" "8001:Voice ASR"; do
    port="${entry%%:*}"
    name="${entry#*:}"
    if curl -s --max-time 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
        PASS=$((PASS + 1))
    fi
done
echo "$PASS/6 services running."
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
    # Belt and suspenders: kill by port
    for port in 8000 8001 8002 8003 8004 8005; do
        pid=$(netstat -ano 2>/dev/null | grep "0.0.0.0:${port}" | grep "LISTEN" | awk '{print $NF}' | head -1)
        if [ -n "$pid" ] && [ "$pid" != "0" ]; then
            taskkill //F //PID "$pid" >/dev/null 2>&1 || true
        fi
    done
    echo "All services stopped."
    exit 0
}
trap cleanup INT TERM

wait
