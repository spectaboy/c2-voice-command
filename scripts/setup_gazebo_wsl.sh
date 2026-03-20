#!/usr/bin/env bash
set -e

echo "=============================================="
echo "  ArduPilot SITL + Gazebo Harmonic Setup"
echo "  WSL2 Ubuntu 24.04"
echo "=============================================="

# 1. System update
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# 2. Install ArduPilot SITL dependencies
echo "[2/6] Installing ArduPilot SITL..."
sudo apt install -y git python3-pip python3-dev python3-venv
sudo apt install -y build-essential ccache g++ gawk gcc-arm-none-eabi

if [ ! -d "$HOME/ardupilot" ]; then
    cd ~
    git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git
    cd ardupilot
    Tools/environment_install/install-prereqs-ubuntu.sh -y
else
    echo "  ardupilot already cloned"
    cd ~/ardupilot
fi

# Reload profile for path updates
. ~/.profile 2>/dev/null || true

# Build ArduCopter SITL
echo "  Building ArduCopter SITL..."
cd ~/ardupilot
./waf configure --board sitl
./waf copter

echo "  ArduPilot SITL built successfully!"

# 3. Install Gazebo Harmonic
echo "[3/6] Installing Gazebo Harmonic..."
sudo apt install -y lsb-release wget gnupg curl

# Add Gazebo repo
sudo wget -q https://packages.osrfoundation.org/gazebo.gpg \
  -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
  http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null

sudo apt update
sudo apt install -y gz-harmonic

echo "  Gazebo Harmonic installed!"

# 4. Build ardupilot_gazebo plugin
echo "[4/6] Building ArduPilot-Gazebo plugin..."
sudo apt install -y libgz-sim8-dev rapidjson-dev

if [ ! -d "$HOME/gz_ws" ]; then
    mkdir -p ~/gz_ws/src && cd ~/gz_ws/src
    git clone https://github.com/ArduPilot/ardupilot_gazebo.git
    cd ardupilot_gazebo
    mkdir -p build && cd build
    cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
    make -j$(nproc)
else
    echo "  ardupilot_gazebo already built"
fi

# 5. Set environment variables
echo "[5/6] Setting environment variables..."
BASHRC_MARKER="# ArduPilot+Gazebo setup"
if ! grep -q "$BASHRC_MARKER" ~/.bashrc; then
    cat >> ~/.bashrc << 'ENVEOF'

# ArduPilot+Gazebo setup
export PATH=$HOME/ardupilot/Tools/autotest:$PATH
export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/gz_ws/src/ardupilot_gazebo/build
export GZ_SIM_RESOURCE_PATH=$HOME/gz_ws/src/ardupilot_gazebo/models:$HOME/gz_ws/src/ardupilot_gazebo/worlds
ENVEOF
    echo "  Environment variables added to ~/.bashrc"
else
    echo "  Environment variables already set"
fi

source ~/.bashrc 2>/dev/null || true

# 6. Verify installation
echo "[6/6] Verifying installation..."
echo "  ArduPilot: $(which sim_vehicle.py 2>/dev/null || echo 'NOT FOUND - run: source ~/.bashrc')"
echo "  Gazebo: $(which gz 2>/dev/null || echo 'NOT FOUND')"

echo ""
echo "=============================================="
echo "  SETUP COMPLETE!"
echo ""
echo "  To run Gazebo + SITL:"
echo ""
echo "  Terminal 1 (Gazebo):"
echo "    gz sim -v4 -r iris_runway.sdf"
echo ""
echo "  Terminal 2 (SITL Alpha - instance 0):"
echo "    cd ~/ardupilot"
echo "    sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console -I0"
echo ""
echo "  Terminal 3 (SITL Bravo - instance 1):"
echo "    cd ~/ardupilot"
echo "    sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console -I1"
echo ""
echo "  SITL exposes TCP ports:"
echo "    Alpha: 5760 (instance 0)"
echo "    Bravo: 5770 (instance 1)"
echo ""
echo "  To connect from Windows C2 system:"
echo "    Set SITL_HOST to WSL IP (check with: hostname -I)"
echo "=============================================="
