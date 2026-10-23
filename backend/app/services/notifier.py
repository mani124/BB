"""Phone alerts. Fire-and-forget; a no-op unless the channel's env vars are set.

Call ``notify(event, text)`` from anywhere (sync or async code). The send happens on a
single background thread with a short timeout, so the trading loop never waits on the
network. Repeats of the same ``dedupe_key`` inside ``min_interval`` seconds are dropped,
so a flapping feed cannot spam. Secrets are never logged.

Channels implement ``send(text)``; Telegram is the only one so far. Add another class and
list it in ``_build_channels``.
"""
import json
import logging
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 5.0
DEFAULT_MIN_INTERVAL_SECONDS = 300.0
MAX_QUEUED = 20


class Channel(Protocol):
    def send(self, text: str) -> None: ...


class TelegramChannel:
    def __init__(self, token: str, chat_id: str):
        self._token = token
        self._chat_id = chat_id

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        body = json.dumps({"chat_id": self._chat_id, "text": text[:4000]}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=SEND_TIMEOUT_SECONDS):
            pass


def _build_channels() -> list:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return [TelegramChannel(token, chat_id)] if token and chat_id else []


class Notifier:
    def __init__(self, channels: Optional[list] = None, clock=time.monotonic):
        self._channels = _build_channels() if channels is None else channels
        self._clock = clock
        self._last_sent: dict[str, float] = {}
        self._lock = threading.Lock()
        self._pending = 0
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notifier")

    @property
    def enabled(self) -> bool:
        return bool(self._channels)

    def notify(self, event: str, text: str, dedupe_key: Optional[str] = None,
               min_interval: float = DEFAULT_MIN_INTERVAL_SECONDS) -> bool:
        """Queue an alert. Returns True if queued, False if disabled, deduped or dropped."""
        if not self._channels:
            return False
        key = dedupe_key or event
        now = self._clock()
        with self._lock:
            last = self._last_sent.get(key)
            if last is not None and now - last < min_interval:
                return False
            if self._pending >= MAX_QUEUED:
                return False
            if len(self._last_sent) > 500:  # per-trade keys would otherwise accumulate forever
                self._last_sent = {k: t for k, t in self._last_sent.items() if now - t < 86400}
            self._last_sent[key] = now
            self._pending += 1
        try:
            self._pool.submit(self._deliver, event, text, key, now)
        except Exception:
            with self._lock:
                self._pending -= 1
                self._last_sent.pop(key, None)
            return False
        return True

    def _deliver(self, event: str, text: str, key: Optional[str] = None, stamped: Optional[float] = None) -> None:
        delivered = False
        try:
            for ch in self._channels:
                try:
                    ch.send(text)
                    delivered = True
                except Exception as exc:
                    # Type only: the exception text can contain the request URL, which holds the token.
                    logger.warning("Alert '%s' not delivered via %s: %s", event, type(ch).__name__, type(exc).__name__)
        finally:
            with self._lock:
                self._pending -= 1
                # Nothing got through: forget the dedupe stamp so the next identical alert is not suppressed.
                if not delivered and key is not None and self._last_sent.get(key) == stamped:
                    self._last_sent.pop(key, None)


notifier = Notifier()


def notify(event: str, text: str, dedupe_key: Optional[str] = None,
           min_interval: float = DEFAULT_MIN_INTERVAL_SECONDS) -> bool:
    """Module-level hook, e.g. ``notify("loss_cap_hit", "Daily loss cap hit", min_interval=3600)``."""
    return notifier.notify(event, text, dedupe_key, min_interval)


_feed_lock = threading.Lock()
_feed_state = "idle"  # idle (never live) | live | dropped (was live, alert sent)


def report_feed_mode(mode: str) -> None:
    """Alert when a feed that was live drops (any non-live mode), and when it recovers.
    ``closed`` (outside market hours) changes nothing; demo before ever being live is not a drop."""
    global _feed_state
    if mode == "closed":
        return
    with _feed_lock:
        old = _feed_state
        if mode == "live":
            _feed_state = "live"
        elif old == "live":
            _feed_state = "dropped"
    if mode == "live" and old == "dropped":
        notify("feed_up", "Dhan feed recovered: back to live.", min_interval=600)
    elif mode != "live" and old == "live":
        notify("feed_down", f"Dhan feed lost: dashboard is now in {mode} mode.", min_interval=600)


def risk_event_alert(kind: str, details: dict) -> None:
    """Handler for ``paper_trader.on_risk_event``: phone alerts for the loss cap and kill switch."""
    if kind == "loss_cap_tripped":
        book = details.get("book", "?")
        notify(
            "loss_cap_hit",
            f"Daily loss cap hit ({book} book): day P&L {details.get('day_pnl', 0):+,.0f} reached "
            f"-{details.get('limit', 0):,.0f}. New entries are paused until the next IST day.",
            dedupe_key=f"loss_cap:{book}:{details.get('date', '')}",
            min_interval=3600,
        )
    elif kind == "kill_switch_engaged":
        notify("kill_switch_on", "Kill switch ENGAGED: open positions squared off, new entries paused.",
               min_interval=60)
    elif kind == "kill_switch_released":
        notify("kill_switch_off", "Kill switch released: new entries may resume.", min_interval=60)
