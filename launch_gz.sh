#!/usr/bin/env bash
#
# Launch Gazebo Harmonic with the hackathon compound world.
# Run this FIRST, then launch_sitl.sh in another terminal.
#
# Usage:
#   ./launch_gz.sh                   # default world
#   ./launch_gz.sh my_world.sdf      # custom world file
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GZ_PLUGIN_DIR="${SCRIPT_DIR}/ardupilot_gazebo"
WORLD="${1:-${SCRIPT_DIR}/worlds/compound_ops.sdf}"

# Set up Gazebo resource paths
export GZ_SIM_RESOURCE_PATH="${SCRIPT_DIR}/worlds:${GZ_PLUGIN_DIR}/models:${GZ_PLUGIN_DIR}/worlds:${GZ_SIM_RESOURCE_PATH:-}"
export GZ_SIM_SYSTEM_PLUGIN_PATH="${GZ_PLUGIN_DIR}/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"

if [ ! -f "${WORLD}" ]; then
    echo "ERROR: World file not found: ${WORLD}"
    exit 1
fi

echo "══════════════════════════════════════════════════════"
echo " Gazebo Harmonic — UxS Hackathon"
echo ""
echo "  World: $(basename "${WORLD}")"
echo ""

# macOS: gz sim cannot run server + GUI in one process (gz-sim#44).
# Use -s here; open a second terminal and run: gz sim -g
if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "  macOS: this terminal = simulation SERVER only (-s)."
  echo "  Open another terminal and run:  gz sim -g"
  echo ""
  echo "  Next: SITL (arducopter) then C2 backend — see OPERATIONS.md"
  echo "══════════════════════════════════════════════════════"
  echo ""
  exec gz sim -s -v4 -r "${WORLD}"
else
  echo "  Next: run SITL / C2 — see OPERATIONS.md"
  echo "══════════════════════════════════════════════════════"
  echo ""
  exec gz sim -v4 -r "${WORLD}"
fi
