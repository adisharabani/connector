#!/bin/bash

# Exit on any error
set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Get the actual user (works even when run with sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

echo "Installing system dependencies..."
apt install mosquitto-clients
#apt install -y netcat python3-venv python3-full

echo "Creating system-wide virtual environment in /opt/connector..."
python3 -m venv /opt/connector

echo "Installing Python dependencies..."
/opt/connector/bin/pip install pyyaml google-cloud-texttospeech pytimeparse

echo "Making main.py executable..."
chmod +x "$SCRIPT_DIR/main.py"


#build raop_play
orig_dir="$PWD"
cd "$SCRIPT_DIR/services/libraop/"
apt-get install build-essential cmake  libssl-dev
git submodule update --force --recursive --init --remote
mkdir -p build
cd build
cmake ..
make
cd $orig_dir


# Create the systemd service file
echo "Creating systemd service file..."
cat > /etc/systemd/system/connector.service << EOL
[Unit]
Description=Home Automation Connector Service
After=network.target

[Service]
Type=simple
User=$ACTUAL_USER
ExecStart=/opt/connector/bin/python $SCRIPT_DIR/main.py
WorkingDirectory=$SCRIPT_DIR
StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd to recognize the new service
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable the service to start on boot
echo "Enabling connector service..."
systemctl enable connector.service

# Start the service
echo "Starting connector service..."
systemctl restart connector.service

echo "Installation complete! Service status:"
systemctl status connector.service 
