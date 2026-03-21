#!/usr/bin/env bash
#
# Launch ArduPilot SITL and connect to the running Gazebo instance.
# Run launch_gz.sh FIRST in another terminal.
#
# Usage:
#   ./launch_sitl.sh               # ArduCopter (default)
#   ./launch_sitl.sh copter        # ArduCopter
#   ./launch_sitl.sh rover         # ArduRover
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARDUPILOT_DIR="${SCRIPT_DIR}/ardupilot"
GZ_PLUGIN_DIR="${SCRIPT_DIR}/ardupilot_gazebo"
VEHICLE="${1:-copter}"

# Set up Gazebo resource paths
export GZ_VERSION=harmonic
export GZ_SIM_RESOURCE_PATH="${SCRIPT_DIR}/worlds:${GZ_PLUGIN_DIR}/models:${GZ_PLUGIN_DIR}/worlds:${GZ_SIM_RESOURCE_PATH:-}"
export GZ_SIM_SYSTEM_PLUGIN_PATH="${GZ_PLUGIN_DIR}/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"

# Resolve vehicle type and frame
case "${VEHICLE}" in
    copter|quad|multirotor)
        VEHICLE_TYPE="ArduCopter"
        FRAME="gazebo-iris"
        ;;
    rover|ugv|ground)
        VEHICLE_TYPE="Rover"
        FRAME="gazebo-rover"
        ;;
    *)
        echo "Unknown vehicle: ${VEHICLE}"
        echo "Usage: ./launch_sitl.sh [copter|rover]"
        exit 1
        ;;
esac

# Check sim_vehicle.py is available
SIM_VEHICLE="${ARDUPILOT_DIR}/Tools/autotest/sim_vehicle.py"
if [ ! -f "${SIM_VEHICLE}" ]; then
    echo "ERROR: sim_vehicle.py not found at ${SIM_VEHICLE}"
    echo "Run ./install.sh first."
    exit 1
fi

echo "══════════════════════════════════════════════════════"
echo " ArduPilot SITL — ${VEHICLE_TYPE}"
echo ""
echo "  Frame:  ${FRAME}"
echo "  Model:  JSON (Gazebo physics backend)"
echo ""
echo "  Connect (multiple clients OK):"
echo "    mavutil.mavlink_connection('mcast:')"
echo "══════════════════════════════════════════════════════"
echo ""

# Launch SITL via sim_vehicle.py
#   --mcast: UDP multicast on 239.255.145.50:14550 (unlimited clients)
exec "${SIM_VEHICLE}" \
    -v "${VEHICLE_TYPE}" \
    -f "${FRAME}" \
    --model JSON \
    --no-rebuild \
    -l 32.990,-106.975,1400,0 \
    --no-mavproxy \
    --mcast
