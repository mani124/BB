"""Trading sessions for the commodity (MCX) and currency (NSE currency derivatives) books, in IST.

``market_hours`` stays the single source for the NSE cash / F&O session and the NSE holiday list; this module
adds the two other exchanges the Commodities & Currency book trades. All decisions go through
``market_hours.now_ist()`` so tests can inject a clock the same way.

* MCX commodity options: Mon-Fri 09:00 to 23:30 IST (23:55 while the US is on daylight saving time, which
  is why the close is a setting, not a constant). On NSE holidays the morning session is closed but the
  evening session (17:00 onwards) usually runs, except on the few days MCX shuts completely.
* NSE currency derivatives (USDINR ...): Mon-Fri 09:00 to 17:00 IST, closed on NSE holidays.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

from app.services import market_hours

MCX = "MCX"
CURRENCY = "CURRENCY"
EXCHANGES = (MCX, CURRENCY)

# Days MCX is closed for BOTH sessions. EDIT ME: best-effort 2026 list, confirm against the MCX holiday circular
# and extend each year. An NSE holiday that is not listed here is treated as "morning closed, evening open".
MCX_FULL_CLOSED: frozenset[date] = frozenset({
    date(2026, 1, 26),   # Republic Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 12, 25),  # Christmas
})

MCX_EVENING_START = time(17, 0)


def parse_hhmm(value: str, default: time) -> time:
    try:
        hh, mm = str(value).strip().split(":")[:2]
        return time(int(hh), int(mm))
    except Exception:
        return default


@dataclass(frozen=True)
class SessionConfig:
    """Per-exchange times (HH:MM strings, IST). Built from runtime settings by ``config_from``."""
    mcx_open: str = "09:00"
    mcx_close: str = "23:30"
    mcx_entry_cutoff: str = "22:30"
    mcx_square_off: str = "23:15"
    cur_open: str = "09:00"
    cur_close: str = "17:00"
    cur_entry_cutoff: str = "16:15"
    cur_square_off: str = "16:50"

    def times(self, exchange: str) -> tuple[time, time, time, time]:
        """(open, close, entry cutoff, square-off) for ``exchange``."""
        if exchange == MCX:
            return (parse_hhmm(self.mcx_open, time(9, 0)), parse_hhmm(self.mcx_close, time(23, 30)),
                    parse_hhmm(self.mcx_entry_cutoff, time(22, 30)), parse_hhmm(self.mcx_square_off, time(23, 15)))
        if exchange == CURRENCY:
            return (parse_hhmm(self.cur_open, time(9, 0)), parse_hhmm(self.cur_close, time(17, 0)),
                    parse_hhmm(self.cur_entry_cutoff, time(16, 15)), parse_hhmm(self.cur_square_off, time(16, 50)))
        raise ValueError(f"unknown exchange {exchange!r}")


def config_from(runtime) -> SessionConfig:
    """Build a SessionConfig from a RuntimeSettings (keys cx_mcx_* / cx_cur_*)."""
    g = runtime.get
    return SessionConfig(
        mcx_open=str(g("cx_mcx_open")), mcx_close=str(g("cx_mcx_close")),
        mcx_entry_cutoff=str(g("cx_mcx_entry_cutoff")), mcx_square_off=str(g("cx_mcx_square_off")),
        cur_open=str(g("cx_cur_open")), cur_close=str(g("cx_cur_close")),
        cur_entry_cutoff=str(g("cx_cur_entry_cutoff")), cur_square_off=str(g("cx_cur_square_off")),
    )


def _now(now: Optional[datetime]) -> datetime:
    if now is None:
        return market_hours.now_ist()
    return now if now.tzinfo else now.replace(tzinfo=market_hours.IST)


def _year_known(d: date) -> bool:
    # Same fail-closed rule as the NSE list: no holiday data for the year means do not trade.
    return d.year in market_hours.NSE_HOLIDAY_YEARS or market_hours.settings.ASSUME_WEEKDAYS_WITHOUT_HOLIDAY_LIST


def trading_windows(exchange: str, d: date, cfg: SessionConfig = SessionConfig()) -> list[tuple[time, time]]:
    """Open windows (start, end) of ``exchange`` on date ``d``; empty when closed all day."""
    if d.weekday() >= 5 or not _year_known(d):
        return []
    opn, close, _entry, _sq = cfg.times(exchange)
    nse_holiday = d in market_hours.NSE_HOLIDAYS
    if exchange == CURRENCY:
        return [] if nse_holiday else [(opn, close)]
    if d in MCX_FULL_CLOSED:
        return []
    if nse_holiday:
        return [(max(MCX_EVENING_START, opn), close)]
    return [(opn, close)]


def is_session_open(exchange: str, now: Optional[datetime] = None, cfg: SessionConfig = SessionConfig()) -> bool:
    n = _now(now)
    return any(s <= n.time() < e for s, e in trading_windows(exchange, n.date(), cfg))


def is_entry_allowed(exchange: str, now: Optional[datetime] = None, cfg: SessionConfig = SessionConfig()) -> bool:
    """Session open and before the exchange's entry cutoff."""
    n = _now(now)
    cutoff = cfg.times(exchange)[2]
    return any(s <= n.time() < min(e, cutoff) for s, e in trading_windows(exchange, n.date(), cfg))


def is_square_off_due(exchange: str, now: Optional[datetime] = None, cfg: SessionConfig = SessionConfig()) -> bool:
    """True from the exchange's square-off time until its close, and any time the exchange is closed
    (nothing is carried overnight)."""
    n = _now(now)
    windows = trading_windows(exchange, n.date(), cfg)
    if not windows:
        return True
    t = n.time()
    sq = cfg.times(exchange)[3]
    if t >= sq:
        return True
    return not any(s <= t < e for s, e in windows)


def any_session_open(now: Optional[datetime] = None, cfg: SessionConfig = SessionConfig()) -> bool:
    return any(is_session_open(x, now, cfg) for x in EXCHANGES)
