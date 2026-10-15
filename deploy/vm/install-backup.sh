#!/usr/bin/env bash
# Installs the nightly backup timer. Run on the VM as root with the bucket name:
#   sudo BUCKET=my-bucket bash install-backup.sh        (from a checkout), or via SRC_DIR for tests.
# Touches only: /usr/local/bin/bb-backup, bb-backup.service/.timer, /etc/bb-backup. No app restart, no other services.
set -euo pipefail
BUCKET="${BUCKET:?set BUCKET=<bucket name, no gs://>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SRC_DIR:-$HERE}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
CONF_DIR="${CONF_DIR:-/etc/bb-backup}"
APP_DIR="${APP_DIR:-/home/mani_vutla7/BB_OPTIONS_DASHBOARD}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
[ "$(id -u)" = 0 ] || { echo "Run as root (use sudo)."; exit 1; }
mkdir -p "$BIN_DIR" "$UNIT_DIR" "$CONF_DIR"
install -m 0755 "$SRC_DIR/bb-backup.sh" "$BIN_DIR/bb-backup"
install -m 0644 "$SRC_DIR/bb-backup.service" "$UNIT_DIR/bb-backup.service"
install -m 0644 "$SRC_DIR/bb-backup.timer" "$UNIT_DIR/bb-backup.timer"
[[ "$BUCKET" =~ ^[a-z0-9._-]+$ ]] || { echo "Invalid BUCKET name (use the bare bucket name, no gs://)."; exit 1; }
[[ "$APP_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "Invalid APP_DIR path."; exit 1; }
printf 'BUCKET=%q\nAPP_DIR=%q\n' "$BUCKET" "$APP_DIR" > "$CONF_DIR/config"
"$SYSTEMCTL" daemon-reload
"$SYSTEMCTL" enable --now bb-backup.timer
echo "Installed. Test now with: sudo bb-backup ; then: bb-backup --status"
