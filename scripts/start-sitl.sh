#!/bin/bash
###############################################################################
# Start 6 ArduPilot SITL instances for the C2 Voice Command demo.
#
# Usage (from project root):
#   bash scripts/start-sitl.sh
#
# This script auto-detects:
#   1. Local sim_vehicle.py install  → runs directly
#   2. WSL2 with ArduPilot installed → launches via wsl.exe
#   3. Docker installed              → runs SITL containers
#   4. Nothing found                 → prints install instructions
###############################################################################

set -e

LOCATION="44.6488,-63.5752,0,0"

#------------------------------------------------------------------------------
# Option 1: Local sim_vehicle.py
#------------------------------------------------------------------------------
SIM_VEHICLE=""
if command -v sim_vehicle.py &>/dev/null; then
    SIM_VEHICLE="sim_vehicle.py"
elif [ -f "$HOME/ardupilot/Tools/autotest/sim_vehicle.py" ]; then
    SIM_VEHICLE="$HOME/ardupilot/Tools/autotest/sim_vehicle.py"
fi

if [ -n "$SIM_VEHICLE" ]; then
    echo "=== Using local ArduPilot SITL ==="
    bash "$HOME/start-c2-sitl.sh" 2>/dev/null || {
        echo "Launching 6 SITL instances..."
        $SIM_VEHICLE -v ArduCopter -I0 --sysid 1 -L "$LOCATION" --no-extra-ports --no-mavproxy -D &
        sleep 2
        $SIM_VEHICLE -v ArduCopter -I1 --sysid 2 -L "$LOCATION" --no-extra-ports --no-mavproxy -D &
        sleep 2
        $SIM_VEHICLE -v ArduCopter -I2 --sysid 3 -L "$LOCATION" --no-extra-ports --no-mavproxy -D &
        sleep 2
        $SIM_VEHICLE -v Rover -I3 --sysid 4 -L "$LOCATION" --no-extra-ports --no-mavproxy -D &
        sleep 2
        $SIM_VEHICLE -v Rover -I4 --sysid 5 -L "$LOCATION" --no-extra-ports --no-mavproxy -D &
        sleep 2
        $SIM_VEHICLE -v Rover -f motorboat -I5 --sysid 6 -L "$LOCATION" --no-extra-ports --no-mavproxy -D &
        echo "All 6 SITL instances started. Press Ctrl+C to stop."
        wait
    }
    exit 0
fi

#------------------------------------------------------------------------------
# Option 2: WSL2 with ArduPilot
#------------------------------------------------------------------------------
if command -v wsl.exe &>/dev/null 2>&1 || command -v wsl &>/dev/null 2>&1; then
    WSL_CMD="wsl.exe"
    command -v wsl.exe &>/dev/null 2>&1 || WSL_CMD="wsl"

    # Check if ArduPilot is installed in WSL
    WSL_HAS_AP=$($WSL_CMD -d Ubuntu -- bash -c "[ -f ~/ardupilot/Tools/autotest/sim_vehicle.py ] && echo yes || echo no" 2>/dev/null || echo "no")

    if [ "$WSL_HAS_AP" = "yes" ]; then
        echo "=== Using ArduPilot SITL in WSL2 ==="

        # Check if launcher exists
        WSL_HAS_LAUNCHER=$($WSL_CMD -d Ubuntu -- bash -c "[ -f ~/start-c2-sitl.sh ] && echo yes || echo no" 2>/dev/null || echo "no")

        if [ "$WSL_HAS_LAUNCHER" = "yes" ]; then
            echo "Running ~/start-c2-sitl.sh in WSL..."
            $WSL_CMD -d Ubuntu -- bash ~/start-c2-sitl.sh
        else
            echo "Running sim_vehicle.py instances in WSL..."
            $WSL_CMD -d Ubuntu -- bash -c "
                export PATH=\"\$HOME/.local/bin:\$HOME/ardupilot/Tools/autotest:\$PATH\"
                cd \$HOME/ardupilot/ArduCopter

                PIDS=()
                trap 'kill \${PIDS[@]} 2>/dev/null; pkill -f arducopter 2>/dev/null; pkill -f ardurover 2>/dev/null; exit 0' INT TERM

                sim_vehicle.py -v ArduCopter -I0 --sysid 1 -L $LOCATION --no-extra-ports --no-mavproxy --out=tcpin:0.0.0.0:5760 -D &>/dev/null &
                PIDS+=(\$!); sleep 2
                sim_vehicle.py -v ArduCopter -I1 --sysid 2 -L $LOCATION --no-extra-ports --no-mavproxy --out=tcpin:0.0.0.0:5770 -D &>/dev/null &
                PIDS+=(\$!); sleep 2
                sim_vehicle.py -v ArduCopter -I2 --sysid 3 -L $LOCATION --no-extra-ports --no-mavproxy --out=tcpin:0.0.0.0:5780 -D &>/dev/null &
                PIDS+=(\$!); sleep 2
                cd \$HOME/ardupilot/Rover
                sim_vehicle.py -v Rover -I3 --sysid 4 -L $LOCATION --no-extra-ports --no-mavproxy --out=tcpin:0.0.0.0:5790 -D &>/dev/null &
                PIDS+=(\$!); sleep 2
                sim_vehicle.py -v Rover -I4 --sysid 5 -L $LOCATION --no-extra-ports --no-mavproxy --out=tcpin:0.0.0.0:5800 -D &>/dev/null &
                PIDS+=(\$!); sleep 2
                sim_vehicle.py -v Rover -f motorboat -I5 --sysid 6 -L $LOCATION --no-extra-ports --no-mavproxy --out=tcpin:0.0.0.0:5810 -D &>/dev/null &
                PIDS+=(\$!)

                echo 'All 6 SITL instances launched in WSL2.'
                echo 'Ports: 5760 5770 5780 5790 5800 5810'
                echo 'Press Ctrl+C to stop.'
                wait
            "
        fi
        exit 0
    else
        echo "WSL2 Ubuntu found but ArduPilot is not installed."
        echo ""
        echo "Run this in your WSL2 Ubuntu terminal to install:"
        echo ""
        echo "  bash /mnt/c/Users/omara/C2\\ UxS/c2-voice-command/scripts/install-ardupilot-wsl.sh"
        echo ""
        echo "This takes ~15-25 minutes. After it finishes, re-run this script."
        exit 1
    fi
fi

#------------------------------------------------------------------------------
# Option 3: Docker
#------------------------------------------------------------------------------
if command -v docker &>/dev/null; then
    echo "=== Using Docker SITL ==="
    docker pull radarku/ardupilot-sitl 2>/dev/null || true

    for i in 0 1 2 3 4 5; do
        case $i in
            0) NAME="uav1"; VEH="ArduCopter"; SID=1; PORT=5760 ;;
            1) NAME="uav2"; VEH="ArduCopter"; SID=2; PORT=5770 ;;
            2) NAME="uav3"; VEH="ArduCopter"; SID=3; PORT=5780 ;;
            3) NAME="ugv1"; VEH="Rover";      SID=4; PORT=5790 ;;
            4) NAME="ugv2"; VEH="Rover";      SID=5; PORT=5800 ;;
            5) NAME="usv1"; VEH="Rover";      SID=6; PORT=5810 ;;
        esac
        echo "[$((i+1))/6] $NAME ($VEH, sysid=$SID, port=$PORT)"
        docker rm -f "sitl-$NAME" 2>/dev/null || true
        docker run -d --name "sitl-$NAME" -p $PORT:5760 \
            radarku/ardupilot-sitl \
            /ardupilot/Tools/autotest/sim_vehicle.py \
            -v $VEH -I0 --sysid $SID -L "$LOCATION" --no-extra-ports --no-mavproxy
    done
    echo "All 6 Docker containers started."
    exit 0
fi

#------------------------------------------------------------------------------
# Nothing found
#------------------------------------------------------------------------------
echo "ERROR: No ArduPilot SITL, WSL2, or Docker found."
echo ""
echo "Recommended: Install via WSL2 (already installed on this machine):"
echo "  1. Open Ubuntu from Start Menu (or run: wsl -d Ubuntu)"
echo "  2. Run: bash /mnt/c/Users/omara/C2\\ UxS/c2-voice-command/scripts/install-ardupilot-wsl.sh"
echo "  3. After install, run: bash ~/start-c2-sitl.sh"
echo ""
exit 1
