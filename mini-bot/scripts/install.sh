#!/usr/bin/env bash
set -euo pipefail

SYSTEMD_DIR=/etc/systemd/system
PROJECT_DIR=/opt/minibot

sudo mkdir -p "$PROJECT_DIR"
sudo rsync -a --exclude '.git' --exclude 'data/mini.db' ./ "$PROJECT_DIR"/

sudo cp deploy/minibot.service "$SYSTEMD_DIR/"
sudo cp deploy/minibot.timer "$SYSTEMD_DIR/"

sudo systemctl daemon-reload
sudo systemctl enable --now minibot.timer

echo "MiniBot timer installed. Check status with: systemctl status minibot.timer"
