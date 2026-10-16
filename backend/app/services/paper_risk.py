"""Daily loss cap and kill switch for new paper entries.

* Daily loss cap: once a book's P&L for the IST day (realised, net of charges, plus open positions
  marked to market net of estimated exit charges) reaches -DAILY_LOSS_LIMIT, new entries in that book
  are refused for the rest of the day. The trip is latched (a recovering open position does not
  re-enable entries) and stored, so a restart on the same day keeps it. It lapses on the next IST date.
* Kill switch: a manual, global stop. While engaged no new entry is taken in any book; engaging it also
  squares off open positions (done by the API so closes use server-owned quotes). It stays engaged,
  across days and restarts, until it is explicitly released.
"""
import json
import logging
from typing import Optional

from pydantic import BaseModel

from app.core.config import settings
from app.services import market_hours
from app.services.strategy_engine import is_setup11
from app.services.paper_models import _now_stamp, _parse_iso

logger = logging.getLogger(__name__)

KILL_SWITCH_EXIT = "KILL_SWITCH"


class RiskStatus(BaseModel):
    daily_loss_limit: float = 0.0  # 0 = cap disabled
    day_pnl: float = 0.0  # net P&L for today's IST date in this view
    loss_cap_tripped: bool = False
    loss_cap_reason: Optional[str] = None
    kill_switch_active: bool = False
    kill_switch_since: Optional[str] = None
    entries_blocked: bool = False
    block_reason: Optional[str] = None


class PaperRiskMixin:
    def _init_risk(self) -> None:
        self._daily_loss_limit: float = max(0.0, float(getattr(settings, "DAILY_LOSS_LIMIT", 0) or 0))
        self._kill_switch: bool = False
        self._kill_switch_since: Optional[str] = None
        self._loss_cap_trips: dict[str, str] = {}  # book ("live"/"demo") -> IST date it tripped
        # Optional callback(kind, details) for alerting, e.g. kind "loss_cap_tripped",
        # "kill_switch_engaged", "kill_switch_released". Left unset until something subscribes.
        self.on_risk_event = None

    def _load_risk(self) -> None:
        if not self.storage:
            return
        raw = self.storage.load_setting("daily_loss_limit")
        if raw is not None:
            try:
                self._daily_loss_limit = max(0.0, float(raw))
            except ValueError:
                pass
        self._kill_switch = (self.storage.load_setting("kill_switch") or "").lower() == "true"
        self._kill_switch_since = self.storage.load_setting("kill_switch_since") or None
        try:
            trips = json.loads(self.storage.load_setting("loss_cap_trips") or "{}")
            self._loss_cap_trips = {str(k): str(v) for k, v in trips.items()} if isinstance(trips, dict) else {}
        except ValueError:
            self._loss_cap_trips = {}

    def _emit_risk_event(self, kind: str, details: dict) -> None:
        cb = self.on_risk_event
        if cb is None:
            return
        try:
            cb(kind, details)
        except Exception:
            logger.warning("on_risk_event callback failed for %s", kind, exc_info=True)

    @staticmethod
    def _today_iso() -> str:
        return market_hours.now_ist().date().isoformat()

    def day_pnl(self, book: Optional[str] = None, pool: Optional[str] = "main") -> float:
        """Net P&L for today's IST date: closed trades exited today, partial profit already booked on
        open runners, and open positions marked to market after estimated exit charges.

        `pool` is "main" (every setup except Setup 11), "s11" (Setup 11 only) or None (everything).
        Setup 11 shadows Setup 5, so its P&L has its own loss cap and never counts toward the main one."""
        from app.services.paper_trader import _outcome_pnl
        today = market_hours.now_ist().date()
        total = 0.0
        def in_pool(p) -> bool:
            return pool is None or (is_setup11(p.setup_type) == (pool == "s11"))

        for p in self._portfolio.closed_trades:
            if p.quarantine_reason or (book and getattr(p, "feed_mode", "demo") != book) or not in_pool(p):
                continue
            ed = _parse_iso(p.exit_datetime)
            if ed is not None and ed.date() == today:
                total += _outcome_pnl(p)
        for p in self._portfolio.active_positions:
            if p.quarantine_reason or (book and getattr(p, "feed_mode", "demo") != book) or not in_pool(p):
                continue
            total += p.booked_pnl_rupees
            total += round(p.pnl_points * p.quantity, 2) - p.est_exit_charges
        return round(total, 2)

    def _check_loss_cap(self, book: str, pool: str = "main") -> bool:
        """Latch the cap for `book` if today's loss has reached the limit. True when tripped today.
        Setup 11 latches under "<book>:s11", so it can stop without stopping the other setups."""
        today = self._today_iso()
        book_key = book if pool == "main" else f"{book}:{pool}"
        if self._loss_cap_trips.get(book_key) == today:
            return True
        limit = self._daily_loss_limit
        if limit <= 0:
            return False
        pnl = self.day_pnl(book, pool)
        if pnl > -limit:
            return False
        self._loss_cap_trips[book_key] = today
        self._loss_cap_trips = {k: v for k, v in self._loss_cap_trips.items() if v == today}
        self._enqueue_write("save_setting", ("loss_cap_trips", json.dumps(self._loss_cap_trips)))
        logger.warning("Daily loss cap tripped (%s book): day P&L %.2f <= -%.2f; new entries blocked until next IST day.",
                       book, pnl, limit)
        self._emit_risk_event("loss_cap_tripped", {"book": book_key, "day_pnl": pnl, "limit": limit, "date": today})
        return True

    def risk_block_reason(self, feed_mode: str, pool: str = "main") -> Optional[str]:
        """Why a new entry in `feed_mode` must be refused by the kill switch or loss cap, else None."""
        if self._kill_switch:
            return "kill switch is engaged"
        if self._check_loss_cap(feed_mode, pool):
            return f"daily loss cap reached{' for Setup 11' if pool == 's11' else ''} (limit {self._daily_loss_limit:,.0f})"
        return None

    def risk_status(self, mode: Optional[str] = None) -> RiskStatus:
        books = [mode] if mode in ("live", "demo") else ["live", "demo"]
        tripped = [b for b in books if self._check_loss_cap(b)]
        pnl = self.day_pnl(mode if mode in ("live", "demo") else None)
        reason = None
        if self._kill_switch:
            reason = "Kill switch engaged"
        elif tripped:
            reason = f"Daily loss cap reached (limit {self._daily_loss_limit:,.0f})"
        return RiskStatus(
            daily_loss_limit=self._daily_loss_limit,
            day_pnl=pnl,
            loss_cap_tripped=bool(tripped),
            loss_cap_reason=f"Day P&L {pnl:,.0f} reached -{self._daily_loss_limit:,.0f}" if tripped else None,
            kill_switch_active=self._kill_switch,
            kill_switch_since=self._kill_switch_since,
            entries_blocked=bool(reason),
            block_reason=reason,
        )

    def set_daily_loss_limit(self, amount: float) -> None:
        """0 disables the cap. Raising the limit mid-day does not clear an already latched trip."""
        self._daily_loss_limit = max(0.0, float(amount))
        self._enqueue_write("save_setting", ("daily_loss_limit", str(self._daily_loss_limit)))

    def set_kill_switch(self, active: bool) -> bool:
        """Engage or release the switch (squaring off is the caller's job). False if nothing changed."""
        if active == self._kill_switch:
            return False
        self._kill_switch = active
        self._kill_switch_since = _now_stamp()[1] if active else None
        self._enqueue_write("save_setting", ("kill_switch", str(active)))
        self._enqueue_write("save_setting", ("kill_switch_since", self._kill_switch_since or ""))
        logger.warning("Kill switch %s", "ENGAGED: new entries paused" if active else "released: entries may resume")
        self._emit_risk_event("kill_switch_engaged" if active else "kill_switch_released",
                              {"since": self._kill_switch_since})
        return True
