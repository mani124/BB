#!/usr/bin/env bash
# One-time installer for the BB auto-deployer. Run on the VM as root:
#   curl -fsSL https://raw.githubusercontent.com/mani124/BB/deploy/deploy/vm/install.sh | sudo bash
# Adds three files in /usr/local/bin, two systemd units (bb-deploy.service / .timer) and /etc/bb-deploy.
# Does not deploy anything, restart anything, or touch other services.
set -euo pipefail

REPO="${REPO:-mani124/BB}"
RAW="${RAW:-https://raw.githubusercontent.com/$REPO/deploy/deploy/vm}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
CONF_DIR="${CONF_DIR:-/etc/bb-deploy}"
APP_DIR="${APP_DIR:-/home/mani_vutla7/BB_OPTIONS_DASHBOARD}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
SRC_DIR="${SRC_DIR:-}"   # tests: copy from a local dir instead of downloading

[ "$(id -u)" = 0 ] || { echo "Run as root (use sudo)."; exit 1; }
[ -d "$APP_DIR/backend" ] || { echo "App not found at $APP_DIR"; exit 1; }
for t in python3 curl; do command -v "$t" >/dev/null || { echo "need $t"; exit 1; }; done

fetch() {  # fetch <name> <dest> <mode>
  if [ -n "$SRC_DIR" ]; then cp "$SRC_DIR/$1" "$2"; else curl -fsSL "$RAW/$1" -o "$2"; fi
  chmod "$3" "$2"
}

mkdir -p "$BIN_DIR" "$UNIT_DIR" "$CONF_DIR"
fetch bb-deploy.sh "$BIN_DIR/bb-deploy" 0755
fetch bb-deploy-approve.sh "$BIN_DIR/bb-deploy-approve" 0755
fetch bb-deploy.service "$UNIT_DIR/bb-deploy.service" 0644
fetch bb-deploy.timer "$UNIT_DIR/bb-deploy.timer" 0644

# Config: created once, never overwritten on re-install.
if [ ! -f "$CONF_DIR/config" ]; then
  dist=""
  # Best effort: if caddy serves the built frontend from a "root" path, use it.
  if [ -f /etc/caddy/Caddyfile ]; then
    dist="$(awk '/options/ {f=1} f && $1=="root" {print $NF; exit}' /etc/caddy/Caddyfile || true)"
  fi
  {
    echo "# bb-deploy settings (see deploy/vm/README.md). Uncomment to change."
    echo "APP_DIR=$APP_DIR"
    if [ -n "$dist" ] && [ -d "$dist" ]; then echo "FRONTEND_DIST=$dist"; else echo "#FRONTEND_DIST=$APP_DIR/frontend/dist"; fi
    echo "#REQUIRE_APPROVAL=1   # 1 = deploy only after: sudo bb-deploy-approve <commit>"
    echo "#PIP_PYTHON=$APP_DIR/venv/bin/python"
  } > "$CONF_DIR/config"
fi

"$SYSTEMCTL" daemon-reload
"$SYSTEMCTL" enable --now bb-deploy.timer

echo
echo "Installed. The VM now checks for a new tested build every 5 minutes."
echo "  Pause:      sudo touch $CONF_DIR/PAUSE      Resume: sudo rm $CONF_DIR/PAUSE"
echo "  Log:        tail -f /var/log/bb-deploy.log"
echo "  Dry run:    sudo bb-deploy --dry-run"
echo "  Uninstall:  curl -fsSL $RAW/uninstall.sh | sudo bash"
echo
# shellcheck disable=SC1091
echo "Frontend files will be replaced in: $(. "$CONF_DIR/config"; echo "${FRONTEND_DIST:-$APP_DIR/frontend/dist}")"
echo "(If caddy serves the website from a different folder, set FRONTEND_DIST in $CONF_DIR/config.)"
