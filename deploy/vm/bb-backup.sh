#!/usr/bin/env bash
# Nightly off-VM backup of trades.db to a private Google Cloud Storage bucket.
# Consistent snapshot (SQLite online backup) -> gzip -> upload -> delete the local temp file.
# Config: /etc/bb-backup/config (BUCKET=..., APP_DIR=..., DB_PATH=...). Needs no keys: uses the VM's service account.
#   bb-backup            run a backup now
#   bb-backup --status   show last success/failure (exit 1 if the last run failed or is >36h old)
set -uo pipefail

CONF="${BB_BACKUP_CONF:-/etc/bb-backup/config}"
STATE_DIR="${STATE_DIR:-/var/lib/bb-backup}"
LOG="${LOG:-/var/log/bb-backup.log}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
APP_DIR="${APP_DIR:-/home/mani_vutla7/BB_OPTIONS_DASHBOARD}"
DB_PATH="${DB_PATH:-$APP_DIR/backend/data/trades.db}"
TMP_DIR="${TMP_DIR:-/var/tmp}"
MIN_FREE_MB="${MIN_FREE_MB:-50}"
UPLOAD_CMD="${UPLOAD_CMD:-}"   # tests only: "<cmd> <src> <gs://dest>"

mkdir -p "$STATE_DIR"
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG" >&2; }

if [ "${1:-}" = "--status" ]; then
  [ -f "$STATE_DIR/last_success" ] && echo "last success: $(cat "$STATE_DIR/last_success")" || echo "never succeeded"
  [ -f "$STATE_DIR/last_failure" ] && echo "last failure: $(cat "$STATE_DIR/last_failure")"
  if [ -f "$STATE_DIR/last_failure" ] && { [ ! -f "$STATE_DIR/last_success" ] || [ "$STATE_DIR/last_failure" -nt "$STATE_DIR/last_success" ]; }; then exit 1; fi
  [ -f "$STATE_DIR/last_success" ] && [ -z "$(find "$STATE_DIR/last_success" -mmin +2160 2>/dev/null)" ] || { echo "STALE: no success in the last 36h"; exit 1; }
  exit 0
fi

fail() { log "FAILED: $*"; echo "$(date -u +%FT%TZ) $*" > "$STATE_DIR/last_failure"; exit 1; }

[ -n "${BUCKET:-}" ] || fail "BUCKET not set in $CONF"
[ -f "$DB_PATH" ] || fail "database not found: $DB_PATH"

free_mb=$(df -Pm "$TMP_DIR" | awk 'NR==2{print $4}')
[ "${free_mb:-0}" -ge "$MIN_FREE_MB" ] || fail "only ${free_mb}MB free in $TMP_DIR (need $MIN_FREE_MB)"

stamp="$(date -u +%Y%m%d-%H%M%S)"
tmp="$(mktemp "$TMP_DIR/trades-$stamp.XXXXXX")"
trap 'rm -f "$tmp" "$tmp.gz"' EXIT

python3 - "$DB_PATH" "$tmp" <<'PY' || fail "sqlite snapshot failed"
import sqlite3, sys
src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=30)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
dst.close(); src.close()
sys.exit(0 if ok == "ok" else 1)
PY
gzip -f "$tmp" || fail "gzip failed"

dest="gs://$BUCKET/trades/trades-$stamp.db.gz"
if [ -n "$UPLOAD_CMD" ]; then
  $UPLOAD_CMD "$tmp.gz" "$dest" >>"$LOG" 2>&1 || fail "upload failed"
elif command -v gcloud >/dev/null; then
  gcloud storage cp --quiet "$tmp.gz" "$dest" >>"$LOG" 2>&1 || fail "upload to $dest failed (see $LOG)"
elif command -v gsutil >/dev/null; then
  gsutil -q cp "$tmp.gz" "$dest" >>"$LOG" 2>&1 || fail "upload to $dest failed (see $LOG)"
else
  fail "neither gcloud nor gsutil found"
fi

size=$(stat -c %s "$tmp.gz")
echo "$stamp $dest" > "$STATE_DIR/last_success"
rm -f "$STATE_DIR/last_failure"
log "OK uploaded $dest (${size} bytes gz)"
