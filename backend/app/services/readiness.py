"""Pre-market readiness: is everything the trading day needs actually in place?

``run_checks`` gathers a list of checks (ok / warn / fail) from the running app and the VM's state files.
``ReadinessMonitor`` sends a phone alert at 09:00 IST on trading days with the result, a reminder at 09:10 and a
last call at 09:20 if the Dhan login is still missing, and an evening alert (18:00) for problems that do not
depend on the market (backup, disk, failed deploy, holiday list). Alerts use ``notifier.notify``, so they are
no-ops until Telegram is configured, which is itself reported as a check.

State files are read-only and optional: on a machine without them (a laptop) the check reports "not available".
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, Optional

from app.core.config import settings
from app.services import market_hours
from app.services.notifier import notifier, notify

logger = logging.getLogger(__name__)

OK, WARN, FAIL = "ok", "warn", "fail"
BACKUP_STATE_DIR = os.getenv("BB_BACKUP_STATE_DIR", "/var/lib/bb-backup")
DEPLOY_STATE_DIR = os.getenv("BB_DEPLOY_STATE_DIR", "/var/lib/bb-deploy")
BACKUP_MAX_AGE_HOURS = 36.0  # same limit as bb-backup --status
RATE_LIMIT_WARN = 50  # Dhan 429s per day before readiness warns
DISK_WARN_PCT, DISK_FAIL_PCT = 80.0, 90.0
# Checks that need the market day to be on; the rest are about the machine and are reported every day.
MARKET_CHECKS = ("dhan_login", "feed")


@dataclass
class Check:
    key: str
    status: str
    detail: str


def _mtime_age_hours(path: str, now: float) -> Optional[float]:
    try:
        return max(0.0, (now - os.path.getmtime(path)) / 3600.0)
    except OSError:
        return None


def check_backup(state_dir: str = BACKUP_STATE_DIR, now: Optional[float] = None) -> Check:
    now = time.time() if now is None else now
    if not os.path.isdir(state_dir):
        return Check("backup", WARN, f"backup state not found at {state_dir} (not a VM, or backup not installed)")
    ok = os.path.join(state_dir, "last_success")
    bad = os.path.join(state_dir, "last_failure")
    ok_age, bad_age = _mtime_age_hours(ok, now), _mtime_age_hours(bad, now)
    if bad_age is not None and (ok_age is None or bad_age < ok_age):
        return Check("backup", FAIL, "the last backup run failed (see /var/log/bb-backup.log)")
    if ok_age is None:
        return Check("backup", FAIL, "no successful backup recorded yet")
    if ok_age > BACKUP_MAX_AGE_HOURS:
        return Check("backup", FAIL, f"last good backup is {ok_age:.0f} h old (limit {BACKUP_MAX_AGE_HOURS:.0f} h)")
    return Check("backup", OK, f"last good backup {ok_age:.1f} h ago")


def check_deploy(state_dir: str = DEPLOY_STATE_DIR) -> Check:
    marker = os.path.join(state_dir, "failed")
    try:
        sha = open(marker).read().strip()
    except OSError:
        return Check("deploy", OK, "no failed deploy recorded")
    return Check("deploy", WARN, f"deploy of {sha[:7] or 'a build'} failed and was rolled back; merge a fix to retry")


def check_disk(path: str, usage: Callable = shutil.disk_usage) -> Check:
    try:
        u = usage(path)
    except OSError as exc:
        return Check("disk", WARN, f"cannot read disk usage for {path}: {type(exc).__name__}")
    pct = u.used / u.total * 100.0 if u.total else 0.0
    free_gb = u.free / 1e9
    text = f"{pct:.0f}% used, {free_gb:.1f} GB free"
    return Check("disk", FAIL if pct >= DISK_FAIL_PCT else WARN if pct >= DISK_WARN_PCT else OK, text)


def run_checks(*, has_dhan_login: bool, feed_live: bool, router_mode: str = "off", broker_session: bool = True,
               kill_switch: bool = False, now: Optional[datetime] = None, data_dir: Optional[str] = None,
               backup_dir: str = BACKUP_STATE_DIR, deploy_dir: str = DEPLOY_STATE_DIR,
               telegram: Optional[bool] = None, rate_limit: Optional[dict] = None) -> list[Check]:
    n = now or market_hours.now_ist()
    out: list[Check] = []
    trading = market_hours.is_trading_day(n.date())
    out.append(Check("trading_day", OK if trading else WARN,
                     "NSE is open today" if trading else "NSE is closed today (weekend or holiday)"))
    missing = market_hours.holiday_list_missing_soon(n.date())
    out.append(Check("holiday_list", FAIL if missing else OK,
                     "next year's NSE holiday list is missing: every day of that year counts as closed"
                     if missing else "NSE holiday list covers this period"))
    out.append(Check("dhan_login", OK if has_dhan_login else FAIL,
                     "Dhan session is connected" if has_dhan_login else "not logged in to Dhan: the dashboard stays in demo mode"))
    out.append(Check("feed", OK if feed_live else WARN,
                     "market data feed is live" if feed_live else "market data feed is not live"))
    out.append(check_backup(backup_dir, now.timestamp() if now else None))
    out.append(check_deploy(deploy_dir))
    out.append(check_disk(data_dir or settings.DATA_DIR))
    tg = notifier.enabled if telegram is None else telegram
    out.append(Check("telegram", OK if tg else WARN,
                     "Telegram alerts are configured" if tg else "Telegram is not configured: alerts go nowhere"))
    if router_mode == "live" and not broker_session:
        out.append(Check("live_routing", FAIL, "live routing is ON but there is no broker session"))
    else:
        out.append(Check("live_routing", OK, f"live routing mode: {router_mode}"))
    if rate_limit is not None:
        n429 = int(rate_limit.get("today", 0))
        out.append(Check("dhan_rate_limit", WARN if n429 >= RATE_LIMIT_WARN else OK,
                         f"Dhan returned HTTP 429 (too many requests) {n429} times today"
                         + (" (calls are delayed: check for a retry loop)" if n429 >= RATE_LIMIT_WARN else "")))
    out.append(Check("kill_switch", WARN if kill_switch else OK,
                     "kill switch is ENGAGED: no new entries" if kill_switch else "kill switch is off"))
    return out


def summarize(checks: list[Check]) -> dict:
    status = FAIL if any(c.status == FAIL for c in checks) else WARN if any(c.status == WARN for c in checks) else OK
    return {"status": status, "checks": [asdict(c) for c in checks]}


def format_report(checks: list[Check], title: str) -> str:
    icon = {OK: "OK  ", WARN: "WARN", FAIL: "FAIL"}
    lines = [title] + [f"{icon[c.status]} {c.key}: {c.detail}" for c in checks if c.status != OK]
    if len(lines) == 1:
        lines.append("Everything is ready.")
    return "\n".join(lines)


class ReadinessMonitor:
    """Decides which readiness alerts are due at a given IST time. Each alert goes out once per day."""

    MORNING, REMINDER, LAST_CALL, EVENING = (9, 0), (9, 10), (9, 20), (18, 0)

    def __init__(self, gather: Callable[[], list[Check]], send: Callable[..., bool] = notify):
        self._gather = gather
        self._send = send
        self._sent: set[tuple[str, str]] = set()

    def _once(self, kind: str, day: str, text: str) -> None:
        if (kind, day) in self._sent:
            return
        self._sent.add((kind, day))
        self._send(f"readiness_{kind}", text, dedupe_key=f"readiness:{kind}:{day}", min_interval=3600)

    def tick(self, now: Optional[datetime] = None) -> list[str]:
        """Run once a minute. Returns the kinds of alert sent on this tick (for tests and logs)."""
        n = now or market_hours.now_ist()
        day, hm = n.date().isoformat(), (n.hour, n.minute)
        before = set(self._sent)
        trading = market_hours.is_trading_day(n.date())
        if trading and self.MORNING <= hm < (9, 15) and ("morning", day) not in self._sent:
            checks = self._gather()
            self._once("morning", day, format_report(checks, f"BB readiness {day} 09:00 IST"))
        if trading and self.REMINDER <= hm < (9, 15) and ("reminder", day) not in self._sent:
            checks = self._gather()
            if any(c.key == "dhan_login" and c.status == FAIL for c in checks):
                self._once("reminder", day, "Market opens in minutes and Dhan is not logged in. Open the dashboard and sign in.")
        if trading and self.LAST_CALL <= hm < (15, 0) and ("last_call", day) not in self._sent:
            checks = self._gather()
            if any(c.key == "dhan_login" and c.status == FAIL for c in checks):
                self._once("last_call", day, "Market is open and Dhan is still not logged in: no live trading or signals today until you sign in.")
        if hm >= self.EVENING and ("evening", day) not in self._sent:
            bad = [c for c in self._gather() if c.status == FAIL and c.key not in MARKET_CHECKS]
            self._sent.add(("evening", day))
            if bad:
                self._send("readiness_evening", format_report(bad, f"BB needs attention {day}"),
                           dedupe_key=f"readiness:evening:{day}", min_interval=3600)
        return sorted(k for k, _ in self._sent - before)

    async def run(self, interval: float = 60.0) -> None:
        while True:
            try:
                self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("readiness tick failed", exc_info=True)
            await asyncio.sleep(interval)
