"""Exchange-session helpers (NSE cash / F&O, IST).

All session decisions go through ``now_ist()`` so tests can inject a clock with
``set_clock`` / ``override_clock`` instead of depending on the wall clock.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Iterator, Optional, Union

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# NSE trading holidays (weekday closures only; weekends are handled separately).
# EDIT ME: best-effort list for 2026, verify against the NSE holiday circular
# and extend each year. Dates not listed here are treated as trading days.
NSE_HOLIDAYS: frozenset[date] = frozenset({
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 3),    # Holi
    date(2026, 3, 26),   # Ram Navami
    date(2026, 3, 31),   # Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 10),  # Diwali Balipratipada
    date(2026, 11, 24),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
})

# Years the list above covers. A date in any other year is treated as a NON-trading day
# (fail closed): trading on an unlisted holiday means trading on frozen quotes.
# When NSE publishes next year's circular, add its dates above and the year here.
NSE_HOLIDAY_YEARS: frozenset[int] = frozenset({2026})
_warned_missing_years: set[int] = set()

_Clock = Callable[[], datetime]
_clock: Optional[_Clock] = None


def _parse_hhmm(value: str, default: time) -> time:
    try:
        hh, mm = str(value).strip().split(":")[:2]
        return time(int(hh), int(mm))
    except Exception:
        return default


def entry_cutoff_time() -> time:
    return _parse_hhmm(settings.ENTRY_CUTOFF_TIME, time(15, 15))


def expiry_day_cutoff_time() -> time:
    return _parse_hhmm(settings.EXPIRY_DAY_CUTOFF_TIME, time(14, 30))


def square_off_time() -> time:
    return _parse_hhmm(settings.EOD_SQUARE_OFF_TIME, time(15, 20))


def set_clock(clock: Union[_Clock, datetime, None]) -> None:
    """Inject a clock (callable or fixed datetime). ``None`` restores the real clock."""
    global _clock
    if clock is None or callable(clock):
        _clock = clock
    else:
        fixed = clock
        _clock = lambda: fixed


@contextmanager
def override_clock(clock: Union[_Clock, datetime]) -> Iterator[None]:
    global _clock
    prev = _clock
    set_clock(clock)
    try:
        yield
    finally:
        _clock = prev


def now_ist() -> datetime:
    """Current time as an IST-aware datetime."""
    raw = _clock() if _clock is not None else datetime.now(IST)
    if raw.tzinfo is None:
        return raw.replace(tzinfo=IST)
    return raw.astimezone(IST)


def now_ist_naive() -> datetime:
    """Current IST wall-clock time without tzinfo (matches the naive-IST candle timestamps)."""
    return now_ist().replace(tzinfo=None)


def _resolve(now: Optional[datetime]) -> datetime:
    if now is None:
        return now_ist()
    if now.tzinfo is None:
        return now.replace(tzinfo=IST)
    return now.astimezone(IST)


def is_trading_day(d: date) -> bool:
    if d.year not in NSE_HOLIDAY_YEARS:
        if d.year not in _warned_missing_years:
            _warned_missing_years.add(d.year)
            logger.error(
                "DATA_QUALITY no NSE holiday list for %s; treating every day as closed until "
                "market_hours.NSE_HOLIDAYS / NSE_HOLIDAY_YEARS are updated", d.year,
            )
        return False
    return d.weekday() < 5 and d not in NSE_HOLIDAYS


def holiday_list_missing_soon(today: Optional[date] = None, days: int = 31) -> bool:
    """True when the holiday list for the year starting within ``days`` days is missing."""
    t = today or now_ist().date()
    return (t + timedelta(days=days)).year not in NSE_HOLIDAY_YEARS


def is_market_open(now: Optional[datetime] = None) -> bool:
    """True on a trading day between 09:15 (inclusive) and 15:30 (exclusive) IST."""
    n = _resolve(now)
    return is_trading_day(n.date()) and MARKET_OPEN <= n.time() < MARKET_CLOSE


def is_entry_allowed(now: Optional[datetime] = None) -> bool:
    """True when new entries may be opened: session open and before the entry cutoff."""
    n = _resolve(now)
    return is_trading_day(n.date()) and MARKET_OPEN <= n.time() < entry_cutoff_time()


def is_square_off_due(now: Optional[datetime] = None) -> bool:
    """True when intraday positions must be closed: at/after the square-off time on a
    trading day, or any time on a non-trading day (nothing may be carried)."""
    n = _resolve(now)
    if not is_trading_day(n.date()):
        return True
    return n.time() >= square_off_time()


def ist_slot_start(now: Optional[datetime] = None, step_min: int = 5) -> datetime:
    """Start of the current ``step_min`` bar slot as an IST-naive datetime
    (matches the naive-IST timestamps produced by the Dhan candle parser)."""
    n = _resolve(now).replace(tzinfo=None, second=0, microsecond=0)
    return n.replace(minute=(n.minute // step_min) * step_min)
