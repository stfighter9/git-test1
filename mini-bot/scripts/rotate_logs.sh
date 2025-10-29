#!/usr/bin/env bash
set -euo pipefail

LOG_DIR=/var/log
LOG_FILE="$LOG_DIR/minibot.log"
BACKUP_DIR="$LOG_DIR/minibot"
MAX_COPIES=7

sudo mkdir -p "$BACKUP_DIR"
if [[ -f "$LOG_FILE" ]]; then
  timestamp=$(date +%Y%m%d%H%M%S)
  sudo cp "$LOG_FILE" "$BACKUP_DIR/minibot-$timestamp.log"
  sudo truncate -s 0 "$LOG_FILE"
fi

cd "$BACKUP_DIR"
ls -1t minibot-*.log | tail -n +$((MAX_COPIES + 1)) | xargs -r sudo rm --
