#!/bin/bash
# ==============================================================================
# ManusTrade - Linux VPS Debian One-Click Setup Script
# Installs Docker, Docker Compose, and starts ManusTrade on Port 3496
# ==============================================================================

set -e

echo "=== [1/4] Updating Debian System Packages ==="
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

echo "=== [2/4] Installing Docker & Docker Compose on Debian ==="
if ! command -v docker &> /dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "[OK] Docker installed successfully."
else
    echo "[OK] Docker is already installed."
fi

echo "=== [3/4] Building ManusTrade Debian Container ==="
sudo docker compose build

echo "=== [4/4] Starting ManusTrade Container in Background ==="
sudo docker compose up -d

SERVER_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')
echo "=================================================================="
echo "[SUCCESS] ManusTrade is running 24/7 on your Debian Linux VPS!"
echo "Web Dashboard URL: http://${SERVER_IP}:3496"
echo "Check Logs command: sudo docker logs -f manustrade_bot"
echo "=================================================================="
