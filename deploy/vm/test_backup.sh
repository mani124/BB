#!/usr/bin/env bash
# Offline test of bb-backup.sh using a fake uploader and temp dirs.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT; fail=0
check() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }
python3 -c "import sqlite3;c=sqlite3.connect('$T/trades.db');c.execute('create table trades(id)');c.execute('insert into trades values(1)');c.commit()"
cat > "$T/up" <<U
#!/usr/bin/env bash
[ -e "$T/broken" ] && exit 1
cp "\$1" "$T/uploaded.gz"
U
chmod +x "$T/up"
run() { BB_BACKUP_CONF=/nonexistent BUCKET="${TB-b}" DB_PATH="$T/trades.db" TMP_DIR="$T" STATE_DIR="$T/st" LOG="$T/log" UPLOAD_CMD="$T/up" "$HERE/bb-backup.sh" "$@" >/dev/null 2>&1; }
run; check "backup succeeds" '[ $? -eq 0 ] || [ -f "$T/st/last_success" ]'
check "uploaded file restores" 'gunzip -c "$T/uploaded.gz" > "$T/r.db" && [ "$(python3 -c "import sqlite3;print(sqlite3.connect(\"$T/r.db\").execute(\"select count(*) from trades\").fetchone()[0])")" = 1 ]'
check "temp removed" '[ -z "$(ls $T/trades-* 2>/dev/null)" ]'
run --status; check "status ok" '[ $? -eq 0 ]'
touch "$T/broken"; run; check "failed upload -> last_failure" '[ -f "$T/st/last_failure" ]'
run --status; check "status reports failure" '[ $? -eq 1 ]'
rm "$T/broken"; TB= run; check "missing bucket fails" '[ -f "$T/st/last_failure" ]'
exit $fail
