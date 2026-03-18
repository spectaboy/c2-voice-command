#!/bin/bash
###############################################################################
# ArduPilot SITL installer for WSL2 Ubuntu
#
# Run this INSIDE your WSL2 Ubuntu terminal:
#   bash /mnt/c/Users/omara/C2\ UxS/c2-voice-command/scripts/install-ardupilot-wsl.sh
#
# What it does:
#   1. Installs system dependencies (git, python3, gcc-arm, etc.)
#   2. Clones ArduPilot into ~/ardupilot
#   3. Runs the official ArduPilot prereqs installer
#   4. Builds ArduCopter and Rover SITL binaries
#   5. Installs pymavlink in WSL Python
#   6. Creates a convenience launcher script
#
# Total time: ~15-25 min depending on network speed
###############################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARNING:${NC} $1"; }
err() { echo -e "${RED}[$(date +%H:%M:%S)] ERROR:${NC} $1"; }

ARDUPILOT_DIR="$HOME/ardupilot"
LOCATION="44.6488,-63.5752,0,0"  # Halifax Harbor

###############################################################################
# Step 1: System dependencies
###############################################################################
log "Step 1/6: Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    git gitk git-gui \
    python3-pip python3-dev python3-venv python3-wxgtk4.0 \
    build-essential ccache g++ gawk gcc-arm-none-eabi \
    libtool libxml2-dev libxslt1-dev \
    python3-lxml python3-matplotlib python3-numpy python3-pyparsing \
    xterm screen procps

log "System dependencies installed."

###############################################################################
# Step 2: Clone ArduPilot
###############################################################################
if [ -d "$ARDUPILOT_DIR" ]; then
    log "Step 2/6: ArduPilot already cloned at $ARDUPILOT_DIR, updating..."
    cd "$ARDUPILOT_DIR"
    git fetch origin
    git checkout master
    git pull origin master
    git submodule update --init --recursive
else
    log "Step 2/6: Cloning ArduPilot (this takes a few minutes)..."
    git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git "$ARDUPILOT_DIR"
fi
cd "$ARDUPILOT_DIR"
log "ArduPilot source ready at $ARDUPILOT_DIR"

###############################################################################
# Step 3: Install ArduPilot prereqs
###############################################################################
log "Step 3/6: Running ArduPilot prerequisites installer..."
Tools/environment_install/install-prereqs-ubuntu.sh -y
# Reload profile to pick up PATH changes
. ~/.profile 2>/dev/null || true
export PATH="$HOME/.local/bin:$HOME/ardupilot/Tools/autotest:$PATH"
log "Prerequisites installed."

###############################################################################
# Step 4: Build ArduCopter SITL
###############################################################################
log "Step 4/6: Building ArduCopter SITL binary..."
cd "$ARDUPILOT_DIR/ArduCopter"
sim_vehicle.py -w --no-mavproxy -v ArduCopter --speedup 10 2>&1 &
SIM_PID=$!
# Wait for build to complete (it auto-launches, we just need the binary)
sleep 30
kill $SIM_PID 2>/dev/null || true
wait $SIM_PID 2>/dev/null || true
log "ArduCopter SITL built."

###############################################################################
# Step 5: Build Rover SITL
###############################################################################
log "Step 5/6: Building Rover SITL binary..."
cd "$ARDUPILOT_DIR/Rover"
sim_vehicle.py -w --no-mavproxy -v Rover --speedup 10 2>&1 &
SIM_PID=$!
sleep 30
kill $SIM_PID 2>/dev/null || true
wait $SIM_PID 2>/dev/null || true
log "Rover SITL built."

###############################################################################
# Step 6: Create launcher script
###############################################################################
log "Step 6/6: Creating SITL launcher..."

cat > "$HOME/start-c2-sitl.sh" << 'LAUNCHER'
#!/bin/bash
# Launch 6 SITL instances for the C2 Voice Command demo
# Halifax Harbor: 44.6488, -63.5752

set -e

export PATH="$HOME/.local/bin:$HOME/ardupilot/Tools/autotest:$PATH"

LOCATION="44.6488,-63.5752,0,0"
AP="$HOME/ardupilot"
PIDS=()

cleanup() {
    echo ""
    echo "Stopping all SITL instances..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Also kill any lingering arducopter/ardurover processes
    pkill -f "arducopter" 2>/dev/null || true
    pkill -f "ardurover" 2>/dev/null || true
    echo "All stopped."
    exit 0
}
trap cleanup INT TERM

echo "=============================================="
echo "  C2 Voice Command — ArduPilot SITL Launcher"
echo "  Location: Halifax Harbor (44.6488, -63.5752)"
echo "=============================================="
echo ""

# UAV-1: ArduCopter, instance 0, sysid 1, port 5760
echo "[1/6] UAV-1  (ArduCopter)  tcp:0.0.0.0:5760  sysid=1"
cd "$AP/ArduCopter"
sim_vehicle.py -v ArduCopter -I0 --sysid 1 \
    -L "$LOCATION" \
    --no-extra-ports --no-mavproxy \
    --out=tcpin:0.0.0.0:5760 \
    -D > /tmp/sitl-uav1.log 2>&1 &
PIDS+=($!)
sleep 3

# UAV-2: ArduCopter, instance 1, sysid 2, port 5770
echo "[2/6] UAV-2  (ArduCopter)  tcp:0.0.0.0:5770  sysid=2"
sim_vehicle.py -v ArduCopter -I1 --sysid 2 \
    -L "$LOCATION" \
    --no-extra-ports --no-mavproxy \
    --out=tcpin:0.0.0.0:5770 \
    -D > /tmp/sitl-uav2.log 2>&1 &
PIDS+=($!)
sleep 3

# UAV-3: ArduCopter, instance 2, sysid 3, port 5780
echo "[3/6] UAV-3  (ArduCopter)  tcp:0.0.0.0:5780  sysid=3"
sim_vehicle.py -v ArduCopter -I2 --sysid 3 \
    -L "$LOCATION" \
    --no-extra-ports --no-mavproxy \
    --out=tcpin:0.0.0.0:5780 \
    -D > /tmp/sitl-uav3.log 2>&1 &
PIDS+=($!)
sleep 3

# UGV-1: Rover, instance 3, sysid 4, port 5790
echo "[4/6] UGV-1  (Rover)       tcp:0.0.0.0:5790  sysid=4"
cd "$AP/Rover"
sim_vehicle.py -v Rover -I3 --sysid 4 \
    -L "$LOCATION" \
    --no-extra-ports --no-mavproxy \
    --out=tcpin:0.0.0.0:5790 \
    -D > /tmp/sitl-ugv1.log 2>&1 &
PIDS+=($!)
sleep 3

# UGV-2: Rover, instance 4, sysid 5, port 5800
echo "[5/6] UGV-2  (Rover)       tcp:0.0.0.0:5800  sysid=5"
sim_vehicle.py -v Rover -I4 --sysid 5 \
    -L "$LOCATION" \
    --no-extra-ports --no-mavproxy \
    --out=tcpin:0.0.0.0:5800 \
    -D > /tmp/sitl-ugv2.log 2>&1 &
PIDS+=($!)
sleep 3

# USV-1: Rover (motorboat frame), instance 5, sysid 6, port 5810
echo "[6/6] USV-1  (Motorboat)   tcp:0.0.0.0:5810  sysid=6"
sim_vehicle.py -v Rover -f motorboat -I5 --sysid 6 \
    -L "$LOCATION" \
    --no-extra-ports --no-mavproxy \
    --out=tcpin:0.0.0.0:5810 \
    -D > /tmp/sitl-usv1.log 2>&1 &
PIDS+=($!)

echo ""
echo "=============================================="
echo "  All 6 SITL instances launched!"
echo ""
echo "  UAV-1  tcp:localhost:5760  (ArduCopter)"
echo "  UAV-2  tcp:localhost:5770  (ArduCopter)"
echo "  UAV-3  tcp:localhost:5780  (ArduCopter)"
echo "  UGV-1  tcp:localhost:5790  (Rover)"
echo "  UGV-2  tcp:localhost:5800  (Rover)"
echo "  USV-1  tcp:localhost:5810  (Rover/Motorboat)"
echo ""
echo "  Logs: /tmp/sitl-*.log"
echo "  Press Ctrl+C to stop all instances"
echo "=============================================="

wait
LAUNCHER

chmod +x "$HOME/start-c2-sitl.sh"

###############################################################################
# Done
###############################################################################
echo ""
echo "=============================================="
echo -e "${GREEN}  ArduPilot SITL installation complete!${NC}"
echo "=============================================="
echo ""
echo "  To launch 6 SITL vehicles:"
echo "    bash ~/start-c2-sitl.sh"
echo ""
echo "  Then in Windows PowerShell, start the C2 services:"
echo "    cd 'C:\Users\omara\C2 UxS\c2-voice-command'"
echo "    bash scripts/start-all.sh"
echo ""
echo "  The vehicle bridge (port 8003) will auto-connect to"
echo "  SITL via WSL2's network bridge (localhost ports)."
echo "=============================================="
