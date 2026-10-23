#!/usr/bin/env bash
# Approve one commit for deploy when REQUIRE_APPROVAL=1:  sudo bb-deploy-approve <commit>
set -euo pipefail
CONF_DIR="${CONF_DIR:-/etc/bb-deploy}"
c="${1:-}"
case "$c" in
  *[!0-9a-f]*|'') echo "usage: bb-deploy-approve <commit sha, at least 7 hex chars>"; exit 1 ;;
esac
[ "${#c}" -ge 7 ] || { echo "need at least 7 characters"; exit 1; }
echo "$c" > "$CONF_DIR/approve"
echo "Approved $c. It deploys on the next check (within 5 minutes) if the market is closed and no position is open."
