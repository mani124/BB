#!/usr/bin/env bash
# bb-deploy: pull-based deployer for the BB options dashboard. Runs from a systemd timer as root.
# It only ever touches: <APP_DIR>/backend/app, <APP_DIR>/frontend/dist, the bb-options service,
# and (when requirements.txt changed) the app's own virtualenv. Nothing else on the machine.
# Every setting below can be overridden in /etc/bb-deploy/config or the environment (tests do this).
set -uo pipefail

CONF_DIR="${CONF_DIR:-/etc/bb-deploy}"
# shellcheck disable=SC1091
[ -f "$CONF_DIR/config" ] && . "$CONF_DIR/config"

APP_DIR="${APP_DIR:-/home/mani_vutla7/BB_OPTIONS_DASHBOARD}"
FRONTEND_DIST="${FRONTEND_DIST:-$APP_DIR/frontend/dist}"
BACKUP_DIR="${BACKUP_DIR:-/home/mani_vutla7/bb-backups}"
STATE_DIR="${STATE_DIR:-/var/lib/bb-deploy}"
LOG_FILE="${LOG_FILE:-/var/log/bb-deploy.log}"
SERVICE="${SERVICE:-bb-options.service}"
REPO="${REPO:-mani124/BB}"
BASE_URL="${BASE_URL:-https://raw.githubusercontent.com/$REPO/deploy}"
TARBALL_URL="${TARBALL_URL:-https://codeload.github.com/$REPO/tar.gz/refs/heads/deploy}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8001/api/health}"
DB_FILE="${DB_FILE:-$APP_DIR/backend/data/trades.db}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
PIP_PYTHON="${PIP_PYTHON:-}"            # auto-detected from the venv when empty
MARKET_START="${MARKET_START:-09:15}"   # IST, inclusive
MARKET_END="${MARKET_END:-15:30}"       # IST, exclusive
REQUIRE_APPROVAL="${REQUIRE_APPROVAL:-0}"
KEEP_BACKUPS="${KEEP_BACKUPS:-10}"
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-60}"
FAKE_NOW_IST="${FAKE_NOW_IST:-}"        # tests only: HH:MM
DRY_RUN="${DRY_RUN:-0}"
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

mkdir -p "$STATE_DIR" "$(dirname "$LOG_FILE")" 2>/dev/null || true

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2; }
die() { log "ERROR: $*"; exit 1; }

# Only one deploy at a time.
exec 9>"$STATE_DIR/lock"
flock -n 9 || { log "another deploy is running, skipping"; exit 0; }

# 1. Kill switch.
if [ -e "$CONF_DIR/PAUSE" ]; then
  log "paused: $CONF_DIR/PAUSE exists, nothing done"
  exit 0
fi

# 2. What is the newest published bundle, and is it newer than what we run?
remote_info="$(curl -fsS --max-time 20 "$BASE_URL/DEPLOY_VERSION")" || die "cannot read $BASE_URL/DEPLOY_VERSION"
remote_sha="$(printf '%s\n' "$remote_info" | sed -n 's/^sha=\([0-9a-f]\{40\}\)$/\1/p')"
remote_built="$(printf '%s\n' "$remote_info" | sed -n 's/^built=\([0-9]\{1,\}\)$/\1/p')"
if [ -z "$remote_sha" ] || [ -z "$remote_built" ]; then die "DEPLOY_VERSION is malformed"; fi

local_sha=""; local_built=0
if [ -f "$STATE_DIR/deployed" ]; then
  local_sha="$(sed -n 's/^sha=//p' "$STATE_DIR/deployed")"
  local_built="$(sed -n 's/^built=//p' "$STATE_DIR/deployed")"
fi
[ "$remote_sha" = "$local_sha" ] && exit 0   # up to date: stay quiet
if [ -f "$STATE_DIR/failed" ] && [ "$(cat "$STATE_DIR/failed")" = "$remote_sha" ]; then
  log "skip ${remote_sha:0:7}: it failed to deploy before (rolled back). Merge a fix to retry."
  exit 0
fi
if [ "$remote_built" -le "${local_built:-0}" ]; then
  log "skip ${remote_sha:0:7}: not newer than deployed ${local_sha:0:7}"
  exit 0
fi
log "candidate ${remote_sha:0:7} (deployed: ${local_sha:0:7})"

# 3. Market hours (IST), compared as minutes since midnight.
now_ist="${FAKE_NOW_IST:-$(TZ=Asia/Kolkata date +%H:%M)}"
to_min() { local h="${1%%:*}" m="${1##*:}"; echo $((10#$h * 60 + 10#$m)); }
if [ "$(to_min "$now_ist")" -ge "$(to_min "$MARKET_START")" ] && [ "$(to_min "$now_ist")" -lt "$(to_min "$MARKET_END")" ]; then
  log "wait: $now_ist IST is inside market hours $MARKET_START-$MARKET_END, will retry"
  exit 0
fi

# 4. No open live paper position and nothing live at the broker (fail safe: if we cannot tell, we do not deploy).
#    Demo rows are synthetic and archived rows are hidden, so neither blocks a deploy. Real-money routing
#    (live_positions / live_orders written by the order router) also blocks: a restart must not interrupt a
#    position held at the broker or an order whose status is still unsettled. Dry-run rows do not block.
if [ -f "$DB_FILE" ]; then
  open_count="$(python3 -I - "$DB_FILE" <<'PY' 2>/dev/null
import sqlite3, sys
con = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True, timeout=10)
cols = {r[1] for r in con.execute("PRAGMA table_info(positions)")}
sql = "SELECT COUNT(*) FROM positions WHERE status IN ('OPEN','TARGET_1')"
if "feed_mode" in cols:
    sql += " AND COALESCE(feed_mode, 'demo') = 'live'"
if "archived_at" in cols:
    sql += " AND archived_at IS NULL"
paper = con.execute(sql).fetchone()[0]
tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "earnings_positions" in tables:  # the earnings book holds positions for days and is not covered by the query above
    paper += con.execute("SELECT COUNT(*) FROM earnings_positions WHERE status='OPEN'").fetchone()[0]
if "swing_positions" in tables:  # the swing book holds positions (and queued entries) for days
    paper += con.execute("SELECT COUNT(*) FROM swing_positions WHERE status IN ('OPEN','PENDING')").fetchone()[0]
routed = orders = 0
if "live_positions" in tables:
    routed = con.execute("SELECT COUNT(*) FROM live_positions WHERE mode='LIVE' AND state IN ('ENTERING','OPEN')").fetchone()[0]
if "live_orders" in tables:
    orders = con.execute("SELECT COUNT(*) FROM live_orders WHERE mode='LIVE' AND status IN ('SENDING','NEW','OPEN','UNKNOWN')").fetchone()[0]
print(paper, routed, orders)
PY
)" || open_count=""
  read -r open_count routed_count order_count <<<"$open_count"
  case "$open_count$routed_count$order_count" in
    ''|*[!0-9]*) log "wait: could not read open positions from $DB_FILE, will retry"; exit 0 ;;
  esac
  if [ "$open_count" -gt 0 ]; then
    log "wait: $open_count open position(s), will retry"
    exit 0
  fi
  if [ "$routed_count" -gt 0 ] || [ "$order_count" -gt 0 ]; then
    log "wait: live routing busy ($routed_count position(s) at the broker, $order_count unsettled order(s)), will retry"
    exit 0
  fi
fi

# 5. Optional manual approval: the file must contain the commit (full or first 7+ chars).
if [ "$REQUIRE_APPROVAL" = "1" ]; then
  approved="$(tr -d '[:space:]' < "$CONF_DIR/approve" 2>/dev/null || true)"
  if [ "${#approved}" -lt 7 ] || [ "${remote_sha#"$approved"}" = "$remote_sha" ]; then
    log "wait: approval required for ${remote_sha:0:7}; run: bb-deploy-approve ${remote_sha:0:7}"
    exit 0
  fi
fi

# 6. Download and sanity-check the bundle.
work="$(mktemp -d "${TMPDIR:-/tmp}/bb-deploy.XXXXXX")"
trap 'rm -rf "$work"' EXIT
curl -fsSL --max-time 120 "$TARBALL_URL" -o "$work/bundle.tgz" || die "download failed"
mkdir "$work/src"
tar -xzf "$work/bundle.tgz" -C "$work/src" --strip-components=1 || die "cannot unpack bundle"
[ "$(sed -n 's/^sha=//p' "$work/src/DEPLOY_VERSION" 2>/dev/null)" = "$remote_sha" ] \
  || { log "bundle changed while downloading, will retry next run"; exit 0; }
for f in backend/app/main.py frontend/dist/index.html backend/requirements.txt; do
  [ -f "$work/src/$f" ] || die "bundle is missing $f"
done

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run: ${remote_sha:0:7} would be deployed now (all checks passed); nothing changed"
  exit 0
fi

# 7. Backup (code, built frontend, and a consistent copy of trades.db).
ts="$(date -u +%Y%m%d-%H%M%S)"
bk="$BACKUP_DIR/deploy-$ts"
mkdir -p "$bk" || die "cannot create backup dir $bk"
cp -a "$APP_DIR/backend/app" "$bk/app" || die "backup of backend/app failed"
[ -d "$FRONTEND_DIST" ] && { cp -a "$FRONTEND_DIST" "$bk/dist" || die "backup of frontend dist failed"; }
cp -a "$APP_DIR/backend/requirements.txt" "$bk/requirements.txt" 2>/dev/null || true
if [ -f "$DB_FILE" ]; then
  python3 -I - "$DB_FILE" "$bk/trades.db" <<'PY' || die "backup of trades.db failed"
import sqlite3, sys
src = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True, timeout=10)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
fi
cp -a "$STATE_DIR/deployed" "$bk/deployed.prev" 2>/dev/null || true
log "backup written to $bk"

owner="$(stat -c '%U:%G' "$APP_DIR")"

# 8. Dependencies, only if requirements.txt changed.
if ! cmp -s "$work/src/backend/requirements.txt" "$APP_DIR/backend/requirements.txt"; then
  py="$PIP_PYTHON"
  if [ -z "$py" ]; then
    for c in "$APP_DIR/venv/bin/python" "$APP_DIR/backend/venv/bin/python" "$APP_DIR/.venv/bin/python"; do
      [ -x "$c" ] && { py="$c"; break; }
    done
  fi
  [ -n "$py" ] || { log "requirements.txt changed but no virtualenv found; set PIP_PYTHON in $CONF_DIR/config. Not deploying."; exit 1; }
  log "requirements.txt changed, installing with $py"
  "$py" -m pip install -q -r "$work/src/backend/requirements.txt" || die "pip install failed (nothing was swapped)"
fi

# 9. Swap the code in (each swap is two renames, so the old copy stays for rollback).
swap_in() {  # swap_in <new> <live>
  rm -rf "$2.old" && mv "$2" "$2.old" && mv "$1" "$2"
}
rollback() {
  log "ROLLING BACK to previous code"
  [ -d "$APP_DIR/backend/app.old" ] && { rm -rf "$APP_DIR/backend/app"; mv "$APP_DIR/backend/app.old" "$APP_DIR/backend/app"; }
  [ -d "$FRONTEND_DIST.old" ] && { rm -rf "$FRONTEND_DIST"; mv "$FRONTEND_DIST.old" "$FRONTEND_DIST"; }
  [ -f "$bk/requirements.txt" ] && cp -a "$bk/requirements.txt" "$APP_DIR/backend/requirements.txt"
  "$SYSTEMCTL" restart "$SERVICE"
  echo "$remote_sha" > "$STATE_DIR/failed"
  log "rolled back; ${remote_sha:0:7} will not be retried"
}

cp -a "$work/src/backend/requirements.txt" "$APP_DIR/backend/requirements.txt"
cp -r "$work/src/backend/app" "$work/app.new"
cp -r "$work/src/frontend/dist" "$work/dist.new"
chown -R "$owner" "$work/app.new" "$work/dist.new" 2>/dev/null || true
mv "$work/app.new" "$APP_DIR/backend/app.new"
mv "$work/dist.new" "$FRONTEND_DIST.new"
swap_in "$APP_DIR/backend/app.new" "$APP_DIR/backend/app" || { rollback; exit 1; }
swap_in "$FRONTEND_DIST.new" "$FRONTEND_DIST" || { rollback; exit 1; }

# 10. Restart only the dashboard service and wait for it to be healthy.
log "restarting $SERVICE"
"$SYSTEMCTL" restart "$SERVICE" || { rollback; exit 1; }
ok=0
for _ in $(seq 1 $((HEALTH_WAIT_SECONDS / 2))); do
  sleep 2
  if "$SYSTEMCTL" is-active --quiet "$SERVICE" && curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
    ok=1; break
  fi
done
if [ "$ok" != 1 ]; then
  log "health check failed after ${HEALTH_WAIT_SECONDS}s"
  rollback
  exit 1
fi

# Re-check it is still up a few seconds later (catches crash-after-start).
sleep 5
if ! "$SYSTEMCTL" is-active --quiet "$SERVICE"; then
  log "service died after start"
  rollback
  exit 1
fi

printf 'sha=%s\nbuilt=%s\ndeployed_at=%s\n' "$remote_sha" "$remote_built" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE_DIR/deployed"
rm -f "$STATE_DIR/failed" "$CONF_DIR/approve"
rm -rf "$APP_DIR/backend/app.old" "$FRONTEND_DIST.old"
# shellcheck disable=SC2012
ls -1dt "$BACKUP_DIR"/deploy-* 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm -rf
log "DEPLOYED ${remote_sha:0:7} OK (backup: $bk)"
