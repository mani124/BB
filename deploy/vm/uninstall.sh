#!/usr/bin/env bash
# Removes the auto-deployer. Leaves the app, trades.db, backups and /var/log/bb-deploy.log alone.
set -euo pipefail
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
CONF_DIR="${CONF_DIR:-/etc/bb-deploy}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
[ "$(id -u)" = 0 ] || { echo "Run as root (use sudo)."; exit 1; }
"$SYSTEMCTL" disable --now bb-deploy.timer 2>/dev/null || true
rm -f "$UNIT_DIR/bb-deploy.service" "$UNIT_DIR/bb-deploy.timer" "$BIN_DIR/bb-deploy" "$BIN_DIR/bb-deploy-approve"
rm -rf "$CONF_DIR" /var/lib/bb-deploy
"$SYSTEMCTL" daemon-reload
echo "Auto-deploy removed. The app and its backups were not touched."
