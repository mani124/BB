#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2015
# Offline test of bb-deploy.sh against a fake app dir, fake "GitHub" (file:// URLs), fake systemctl
# and a fake health endpoint. Touches nothing outside a temp dir.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T="$(mktemp -d)"; trap 'kill $HPID 2>/dev/null; rm -rf "$T"' EXIT
fail=0
check() { if eval "$2"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }

PORT=$((20000 + RANDOM % 10000))
mkdir -p "$T/health" && echo '{"status":"healthy"}' > "$T/health/health"
mkdir -p "$T/health/api" && echo '{"status":"healthy"}' > "$T/health/api/health"
(cd "$T/health" && exec python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1) & HPID=$!
sleep 1

# Fake systemctl: records calls; "active" unless $T/svc_broken exists.
cat > "$T/systemctl" <<SC
#!/usr/bin/env bash
echo "\$*" >> "$T/systemctl.log"
[ "\$1" = is-active ] && { [ ! -e "$T/svc_broken" ]; exit \$?; }
exit 0
SC
chmod +x "$T/systemctl"

make_world() {  # fresh app dir + conf
  rm -rf "$T/app" "$T/conf" "$T/state" "$T/bk"; : > "$T/systemctl.log"; rm -f "$T/svc_broken"
  mkdir -p "$T/app/backend/app" "$T/app/backend/data" "$T/app/frontend/dist" "$T/conf" "$T/state"
  echo old > "$T/app/backend/app/main.py"; echo old > "$T/app/frontend/dist/index.html"
  echo "fastapi" > "$T/app/backend/requirements.txt"; echo "SECRET=1" > "$T/app/.env"
  python3 - "$T/app/backend/data/trades.db" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1]); c.execute("CREATE TABLE positions (id INTEGER, status TEXT)")
c.execute("INSERT INTO positions VALUES (1,'STOP_LOSS')"); c.commit()
PY
}
make_bundle() {  # make_bundle <sha-char> <built>
  local sha; sha="$(printf '%s' "$1" | head -c1 | python3 -c 'import sys;print(sys.stdin.read()*40)')"
  rm -rf "$T/remote" "$T/b"; mkdir -p "$T/remote" "$T/b/deploy-main/backend/app" "$T/b/deploy-main/frontend/dist"
  echo "new-$1" > "$T/b/deploy-main/backend/app/main.py"; echo "new-$1" > "$T/b/deploy-main/frontend/dist/index.html"
  echo "fastapi" > "$T/b/deploy-main/backend/requirements.txt"
  printf 'sha=%s\nbuilt=%s\n' "$sha" "$2" > "$T/b/deploy-main/DEPLOY_VERSION"
  cp "$T/b/deploy-main/DEPLOY_VERSION" "$T/remote/DEPLOY_VERSION"
  tar -C "$T/b" -czf "$T/remote/bundle.tgz" deploy-main
}
run() {
  env CONF_DIR="$T/conf" APP_DIR="$T/app" BACKUP_DIR="$T/bk" STATE_DIR="$T/state" LOG_FILE="$T/log" \
    BASE_URL="file://$T/remote" TARBALL_URL="file://$T/remote/bundle.tgz" SYSTEMCTL="$T/systemctl" \
    HEALTH_URL="http://127.0.0.1:$PORT/api/health" HEALTH_WAIT_SECONDS=4 FAKE_NOW_IST="${NOW:-20:00}" "$@" "$HERE/bb-deploy.sh"
}
content() { cat "$T/app/backend/app/main.py"; }

# Fake venv python: logs pip calls; "pip freeze" prints the old pins; install fails if $T/pip_broken exists.
cat > "$T/py" <<PYF
#!/usr/bin/env bash
echo "\$*" >> "$T/pip.log"
[ "\$3" = freeze ] && { echo "fastapi==0.1"; exit 0; }
[ -e "$T/pip_broken" ] && grep -q -- "-r $T/bk" <<<"\$*" && exit 0
[ -e "$T/pip_broken" ] && exit 1
exit 0
PYF
chmod +x "$T/py"

echo "== happy path"
make_world; make_bundle a 100; NOW=20:00 run >/dev/null 2>&1
check "new code deployed"            '[ "$(content)" = new-a ]'
check "frontend deployed"            '[ "$(cat "$T/app/frontend/dist/index.html")" = new-a ]'
check ".env untouched"               '[ "$(cat "$T/app/.env")" = SECRET=1 ]'
check "trades.db untouched"          'python3 -c "import sqlite3;assert sqlite3.connect(\"$T/app/backend/data/trades.db\").execute(\"select count(*) from positions\").fetchone()[0]==1"'
check "backup has old code + db"     'ls "$T"/bk/deploy-*/app/main.py "$T"/bk/deploy-*/trades.db >/dev/null'
check "only the bb service restarted" '[ "$(grep -c "^restart" "$T/systemctl.log")" = 1 ] && grep -q "^restart bb-options.service" "$T/systemctl.log"'
check "state recorded"               'grep -q "^sha=aaaa" "$T/state/deployed"'
echo "== second run is a no-op"
: > "$T/systemctl.log"; NOW=20:00 run >/dev/null 2>&1
check "no restart when up to date"   '! grep -q restart "$T/systemctl.log"'

echo "== inside market hours"
make_world; make_bundle b 100; NOW=10:00 run >/dev/null 2>&1
check "not deployed at 10:00 IST"    '[ "$(content)" = old ]'
NOW=09:14 run >/dev/null 2>&1;  check "deploys at 09:14"  '[ "$(content)" = new-b ]'
make_world; make_bundle b 100; NOW=15:29 run >/dev/null 2>&1; check "not deployed at 15:29" '[ "$(content)" = old ]'
NOW=15:30 run >/dev/null 2>&1;  check "deploys at 15:30"  '[ "$(content)" = new-b ]'

echo "== open position"
make_world; make_bundle c 100
python3 -c "import sqlite3;c=sqlite3.connect('$T/app/backend/data/trades.db');c.execute(\"insert into positions values (2,'TARGET_1')\");c.commit()"
NOW=20:00 run >/dev/null 2>&1;  check "not deployed with open position" '[ "$(content)" = old ]'
echo "== open demo position only"
make_world; make_bundle 5 100
python3 -c "import sqlite3;c=sqlite3.connect('$T/app/backend/data/trades.db');c.execute('alter table positions add column feed_mode text');c.execute(\"insert into positions values (3,'OPEN','demo')\");c.commit()"
NOW=20:00 run >/dev/null 2>&1;  check "open demo position does not block" '[ "$(content)" = new-5 ]'
make_world; make_bundle 6 100
python3 -c "import sqlite3;c=sqlite3.connect('$T/app/backend/data/trades.db');c.execute('alter table positions add column feed_mode text');c.execute(\"insert into positions values (4,'OPEN','live')\");c.commit()"
NOW=20:00 run >/dev/null 2>&1;  check "open live position blocks" '[ "$(content)" = old ]'
echo "== unreadable db (fail safe)"
echo garbage > "$T/app/backend/data/trades.db"; NOW=20:00 run >/dev/null 2>&1
check "not deployed if db unreadable" '[ "$(content)" = old ]'

echo "== live routing state"
mk_live() {  # $1 positions row, $2 orders row (either may be empty)
  python3 -c "
import sqlite3;c=sqlite3.connect('$T/app/backend/data/trades.db')
c.execute('create table live_positions (position_id text, mode text, state text)')
c.execute('create table live_orders (id integer, mode text, status text)')
[c.execute(q) for q in ['''$1''','''$2'''] if q.strip()]
c.commit()"
}
make_world; make_bundle 8 100; mk_live "insert into live_positions values ('p1','LIVE','OPEN')" ""
NOW=20:00 run >/dev/null 2>&1;  check "position held at broker blocks" '[ "$(content)" = old ]'
make_world; make_bundle 9 100; mk_live "" "insert into live_orders values (1,'LIVE','UNKNOWN')"
NOW=20:00 run >/dev/null 2>&1;  check "unsettled live order blocks" '[ "$(content)" = old ]'
make_world; make_bundle a 100; mk_live "insert into live_positions values ('p2','DRY','OPEN')" "insert into live_orders values (2,'LIVE','COMPLETE')"
NOW=20:00 run >/dev/null 2>&1;  check "dry-run position and settled order do not block" '[ "$(content)" = new-a ]'
echo "== kill switch"
make_world; make_bundle d 100; touch "$T/conf/PAUSE"; NOW=20:00 run >/dev/null 2>&1
check "PAUSE blocks deploy"          '[ "$(content)" = old ]'

echo "== older bundle"
make_world; make_bundle e 100; NOW=20:00 run >/dev/null 2>&1; make_bundle f 50; NOW=20:00 run >/dev/null 2>&1
check "older bundle ignored"         '[ "$(content)" = new-e ]'

echo "== approval mode"
make_world; make_bundle 7 100; NOW=20:00 REQUIRE_APPROVAL=1 run >/dev/null 2>&1
check "not deployed without approval" '[ "$(content)" = old ]'
echo "7777777" > "$T/conf/approve"; NOW=20:00 REQUIRE_APPROVAL=1 run >/dev/null 2>&1
check "deployed after approval"      '[ "$(content)" = new-7 ]'
check "approval consumed"            '[ ! -e "$T/conf/approve" ]'

echo "== failed health check rolls back"
make_world; make_bundle 8 100; touch "$T/svc_broken"; NOW=20:00 run >/dev/null 2>&1
check "old code restored"            '[ "$(content)" = old ] && [ "$(cat "$T/app/frontend/dist/index.html")" = old ]'
check "failed commit remembered"     '[ -f "$T/state/failed" ]'
rm -f "$T/svc_broken"; : > "$T/systemctl.log"; NOW=20:00 run >/dev/null 2>&1
check "failed commit not retried"    '[ "$(content)" = old ] && ! grep -q restart "$T/systemctl.log"'

echo "== dependencies changed, deploy fails health check"
make_world; make_bundle 8 100; : > "$T/pip.log"; rm -f "$T/pip_broken"
echo "fastapi>=1" > "$T/b/deploy-main/backend/requirements.txt"; tar -C "$T/b" -czf "$T/remote/bundle.tgz" deploy-main
touch "$T/svc_broken"; NOW=20:00 PIP_PYTHON="$T/py" run >/dev/null 2>&1; rm -f "$T/svc_broken"
check "packages frozen before install"  'grep -q "pip freeze" "$T/pip.log"'
check "rollback reinstalls old packages" 'grep -q "pip install -q -r $T/bk/deploy-.*/pip-freeze.txt" "$T/pip.log"'
check "old requirements restored"       '[ "$(cat "$T/app/backend/requirements.txt")" = fastapi ]'
echo "== constraints.txt alone changed"
make_world; make_bundle 9 100; : > "$T/pip.log"
echo "fastapi==2.0" > "$T/b/deploy-main/backend/constraints.txt"; tar -C "$T/b" -czf "$T/remote/bundle.tgz" deploy-main
NOW=20:00 PIP_PYTHON="$T/py" run >/dev/null 2>&1
check "constraints change triggers install" 'grep -q -- "-c .*constraints.txt" "$T/pip.log"'
check "constraints copied into the app"   '[ "$(cat "$T/app/backend/constraints.txt")" = fastapi==2.0 ]'
echo "== pip install fails"
make_world; make_bundle 6 100; : > "$T/pip.log"; touch "$T/pip_broken"
echo "fastapi>=1" > "$T/b/deploy-main/backend/requirements.txt"; tar -C "$T/b" -czf "$T/remote/bundle.tgz" deploy-main
NOW=20:00 PIP_PYTHON="$T/py" run >/dev/null 2>&1; rm -f "$T/pip_broken"
check "code not swapped when pip fails"  '[ "$(content)" = old ] && ! grep -q restart "$T/systemctl.log"'
check "packages restored when pip fails" 'grep -q "pip-freeze.txt" "$T/pip.log"'
echo "== dry run"
make_world; make_bundle 9 100; NOW=20:00 run --dry-run >/dev/null 2>&1
check "dry run changes nothing"      '[ "$(content)" = old ] && ! grep -q restart "$T/systemctl.log"'

echo "== install / uninstall into fake dirs"
mkdir -p "$T/inst/bin" "$T/inst/units" "$T/inst/conf"
fakeroot_env=(BIN_DIR="$T/inst/bin" UNIT_DIR="$T/inst/units" CONF_DIR="$T/inst/conf" APP_DIR="$T/app" SYSTEMCTL="$T/systemctl" SRC_DIR="$HERE")
if [ "$(id -u)" = 0 ]; then
  env "${fakeroot_env[@]}" bash "$HERE/install.sh" >/dev/null 2>&1
  check "installer places files"     '[ -x "$T/inst/bin/bb-deploy" ] && [ -f "$T/inst/units/bb-deploy.timer" ] && [ -f "$T/inst/conf/config" ]'
  check "installer enables timer"    'grep -q "enable --now bb-deploy.timer" "$T/systemctl.log"'
  env "${fakeroot_env[@]}" bash "$HERE/uninstall.sh" >/dev/null 2>&1
  check "uninstaller removes files"  '[ ! -e "$T/inst/bin/bb-deploy" ] && [ ! -e "$T/inst/units/bb-deploy.timer" ]'
else
  echo "skip - installer test needs root"
fi

[ "$fail" = 0 ] && echo "ALL PASSED" || { echo "SOME FAILED"; exit 1; }
