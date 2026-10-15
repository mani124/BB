import asyncio
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.strategy_engine import Signal, is_setup5
from app.services.strike_selector import get_lot_size
from app.services import market_hours
from app.core.config import settings
from app.services.paper_models import *  # noqa: F401,F403
from app.services.paper_models import _now_stamp, _parse_iso, _signed_slip, _view_mode  # noqa: F401


class PaperGuardsMixin:
    """Methods split out of PaperTradingEngine (no behaviour change)."""

    @staticmethod
    def _quote_block_reason(rec) -> Optional[str]:
        """P1-3: None if the live quote behind a recommendation is fresh and tradeable."""
        if getattr(settings, "REQUIRE_REAL_DELTA", False) and getattr(rec, "delta_assumed", False):
            return "option exits rely on an assumed delta (no Greeks in chain)"
        if getattr(rec, "lot_size_known", True) is False:
            return "lot size unknown (guessed default); refusing to size a position"
        max_age = float(getattr(settings, "MAX_QUOTE_AGE_SECONDS", 0) or 0)
        age = getattr(rec, "quote_age_s", None)
        as_of = getattr(rec, "quote_as_of", None)
        if as_of is not None:
            # The stored age was frozen when the signal was built; recompute so a stalled scan cannot reuse an old ask.
            age = max(float(age or 0.0), time.time() - float(as_of))
        if max_age > 0 and age is not None and float(age) > max_age:
            return f"quote is {float(age):.0f}s old (limit {max_age:.0f}s)"
        ask = float(getattr(rec, "real_ask_price", 0.0) or 0.0)
        bid = float(getattr(rec, "real_bid_price", 0.0) or 0.0)
        max_spread = float(getattr(settings, "MAX_ENTRY_SPREAD_PCT", 0) or 0)
        if max_spread > 0 and ask > 0 and bid > 0:
            if ask < bid:
                return f"crossed market (bid {bid} > ask {ask})"
            spread_pct = (ask - bid) / ask * 100.0
            if spread_pct > max_spread:
                return f"spread {spread_pct:.1f}% exceeds {max_spread:.0f}% (bid {bid}, ask {ask})"
        return None

    @staticmethod
    def _contract_key(security_id: Optional[str], strike_symbol: Optional[str]) -> Optional[str]:
        if security_id and str(security_id).strip():
            return f"id:{str(security_id).strip()}"
        if strike_symbol and str(strike_symbol).strip():
            return f"sym:{str(strike_symbol).strip()}"
        return None

    def _exposure_block_reason(self, signal: Signal, lots: Optional[int] = None, feed_mode: Optional[str] = None) -> Optional[str]:
        """P0-2: returns why a new entry must be refused, or None if it may proceed.

        Caps are per book: demo positions never count against live limits and vice versa."""
        rec = signal.strike_recommendation
        key = self._contract_key(getattr(rec, "option_security_id", None), getattr(rec, "strike_symbol", None))

        def same_book(p) -> bool:
            return feed_mode is None or getattr(p, "feed_mode", "demo") == feed_mode

        active = [p for p in self._portfolio.active_positions if same_book(p)]
        closed = [p for p in self._portfolio.closed_trades if same_book(p)]
        for p in active:
            if key and self._contract_key(p.option_security_id, p.strike_symbol) == key:
                return f"contract {key} already has an open position"
            if p.symbol == signal.symbol and p.option_type == signal.option_type:
                return f"{p.symbol} {p.option_type} already has an open position"

        # P1-7: portfolio-level caps (0 disables a cap)
        max_open = int(getattr(settings, "MAX_OPEN_POSITIONS", 0) or 0)
        if max_open > 0 and len(active) >= max_open:
            return f"max open positions reached ({max_open})"

        max_notional = float(getattr(settings, "MAX_OPEN_NOTIONAL", 0) or 0)
        if max_notional > 0:
            open_notional = sum(p.option_entry * p.quantity for p in active)
            lots = lots if lots is not None else self._portfolio.default_lots
            new_notional = float(getattr(rec, "estimated_option_entry", 0.0) or 0.0) * int(getattr(rec, "lot_size", 0) or 0) * max(1, lots)
            if open_notional + new_notional > max_notional:
                return f"open premium notional would exceed {max_notional:,.0f}"

        max_per_day = int(getattr(settings, "MAX_ENTRIES_PER_SYMBOL_PER_DAY", 0) or 0)
        if max_per_day > 0:
            today = market_hours.now_ist().date()
            entered = 0
            for p in active + closed:
                if p.symbol != signal.symbol or p.quarantine_reason:
                    continue
                ed = _parse_iso(p.entry_datetime)
                if ed is not None and ed.date() == today:
                    entered += 1
            if entered >= max_per_day:
                return f"{signal.symbol} already had {entered} entries today (limit {max_per_day})"

        cooldown = int(getattr(settings, "REENTRY_COOLDOWN_SECONDS", 0) or 0)
        if cooldown > 0:
            now = market_hours.now_ist()
            for p in reversed(closed):
                if p.symbol != signal.symbol or p.option_type != signal.option_type or p.quarantine_reason:
                    continue
                exited = _parse_iso(p.exit_datetime)
                if exited and timedelta(0) <= (now - exited) < timedelta(seconds=cooldown):
                    return f"cooldown ({cooldown}s) after exit on {p.symbol} {p.option_type}"
        return None

    def flag_stale_carryover(self) -> list[PaperPosition]:
        """P0-5: positions still open from a previous IST date can't be valid intraday
        positions. Close them out as STALE_CARRYOVER (no repricing) and quarantine them
        so they are excluded from performance stats."""
        today = market_hours.now_ist().date()
        stale = []
        for pos in list(self._portfolio.active_positions):
            entered = _parse_iso(pos.entry_datetime)
            if entered is None or entered.date() >= today:
                continue
            _, now_iso = _now_stamp()
            pos.status = "CLOSED"
            pos.exit_reason = STALE_CARRYOVER
            pos.exit_time = _now_stamp()[0]
            pos.exit_datetime = now_iso
            pos.quarantine_reason = STALE_CARRYOVER
            self._portfolio.active_positions.remove(pos)
            self._portfolio.closed_trades.append(pos)
            self._enqueue_write("upsert", pos)
            stale.append(pos)
        if stale:
            logger.warning("Flagged %d stale carried-over position(s) as %s", len(stale), STALE_CARRYOVER)
            self._recalculate_metrics()
        return stale

    def square_off_if_due(self, feed_mode: Optional[str] = "live") -> list[PaperPosition]:
        """P0-5: close open positions once the EOD square-off time is reached."""
        if not market_hours.is_square_off_due():
            return []
        closed = []
        for pos in list(self._portfolio.active_positions):
            if feed_mode is not None and getattr(pos, "feed_mode", "demo") != feed_mode:
                continue
            res = self.close_position(pos.id, reason=EOD_SQUARE_OFF)
            if res:
                closed.append(res)
        return closed
