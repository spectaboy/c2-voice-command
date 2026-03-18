#!/bin/bash
# Launch 6 SITL instances for the C2 Voice Command demo (daemonized)
# Uses raw SITL binaries — processes persist after terminal closes
# Halifax Harbor: 44.6488, -63.5752

AP="$HOME/ardupilot"
LOCATION="44.6488,-63.5752,0,0"
PIDFILE="/tmp/c2-sitl.pids"

COPTER="$AP/build/sitl/bin/arducopter"
ROVER="$AP/build/sitl/bin/ardurover"
COPTER_DEFAULTS="$AP/Tools/autotest/default_params/copter.parm"
ROVER_DEFAULTS="$AP/Tools/autotest/default_params/rover.parm"

# Kill any existing instances first
if [ -f "$PIDFILE" ]; then
    echo "Stopping previous SITL instances..."
    while read pid; do
        kill "$pid" 2>/dev/null || true
    done < "$PIDFILE"
    rm -f "$PIDFILE"
    sleep 1
fi
pkill -f "arducopter" 2>/dev/null || true
pkill -f "ardurover" 2>/dev/null || true
sleep 1

echo "============================================="
echo "  C2 Voice Command — ArduPilot SITL Launcher"
echo "  Location: Halifax Harbor (44.6488, -63.5752)"
echo "============================================="
echo ""

> "$PIDFILE"

# UAV-1: ArduCopter, instance 0, sysid 1, port 5760
echo "[1/6] UAV-1  (ArduCopter)  tcp:0.0.0.0:5760  sysid=1"
nohup $COPTER --home $LOCATION -I0 --sysid 1 --speedup 1 --model quad --defaults $COPTER_DEFAULTS > /tmp/sitl-uav1.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 2

# UAV-2: ArduCopter, instance 1, sysid 2, port 5770
echo "[2/6] UAV-2  (ArduCopter)  tcp:0.0.0.0:5770  sysid=2"
nohup $COPTER --home $LOCATION -I1 --sysid 2 --speedup 1 --model quad --defaults $COPTER_DEFAULTS > /tmp/sitl-uav2.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 2

# UAV-3: ArduCopter, instance 2, sysid 3, port 5780
echo "[3/6] UAV-3  (ArduCopter)  tcp:0.0.0.0:5780  sysid=3"
nohup $COPTER --home $LOCATION -I2 --sysid 3 --speedup 1 --model quad --defaults $COPTER_DEFAULTS > /tmp/sitl-uav3.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 2

# UGV-1: Rover, instance 3, sysid 4, port 5790
echo "[4/6] UGV-1  (Rover)       tcp:0.0.0.0:5790  sysid=4"
nohup $ROVER --home $LOCATION -I3 --sysid 4 --speedup 1 --model rover --defaults $ROVER_DEFAULTS > /tmp/sitl-ugv1.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 2

# UGV-2: Rover, instance 4, sysid 5, port 5800
echo "[5/6] UGV-2  (Rover)       tcp:0.0.0.0:5800  sysid=5"
nohup $ROVER --home $LOCATION -I4 --sysid 5 --speedup 1 --model rover --defaults $ROVER_DEFAULTS > /tmp/sitl-ugv2.log 2>&1 &
echo $! >> "$PIDFILE"
sleep 2

# USV-1: Rover (motorboat), instance 5, sysid 6, port 5810
echo "[6/6] USV-1  (Motorboat)   tcp:0.0.0.0:5810  sysid=6"
nohup $ROVER --home $LOCATION -I5 --sysid 6 --speedup 1 --model motorboat --defaults $ROVER_DEFAULTS > /tmp/sitl-usv1.log 2>&1 &
echo $! >> "$PIDFILE"

sleep 3

# Verify they're running
RUNNING=0
while read pid; do
    if kill -0 "$pid" 2>/dev/null; then
        RUNNING=$((RUNNING + 1))
    fi
done < "$PIDFILE"

echo ""
echo "============================================="
echo "  $RUNNING/6 SITL instances running!"
echo ""
echo "  UAV-1  tcp:localhost:5760  (ArduCopter)"
echo "  UAV-2  tcp:localhost:5770  (ArduCopter)"
echo "  UAV-3  tcp:localhost:5780  (ArduCopter)"
echo "  UGV-1  tcp:localhost:5790  (Rover)"
echo "  UGV-2  tcp:localhost:5800  (Rover)"
echo "  USV-1  tcp:localhost:5810  (Rover/Motorboat)"
echo ""
echo "  PIDs saved to $PIDFILE"
echo "  Logs: /tmp/sitl-*.log"
echo "  Stop: wsl -d Ubuntu bash -c 'bash ~/stop-c2-sitl.sh'"
echo "============================================="
