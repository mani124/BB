"""Builds N minute bars for an instrument from 1 minute history plus live ticks.

The scanner keeps 5 and 15 minute bars itself. Dhan serves no 3 minute candles, so the 3m versions of T315 build their own
bars here: seeded from Dhan 1 minute candles (aggregated), then updated from every live price. Bars are labelled by their
start time on a grid that starts at 09:15, a bar is completed once its end time has passed, and nothing is created outside
market hours. Pure Python and pandas, no I/O.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

import pandas as pd

from app.services import market_hours


def slot_start(ts: datetime, minutes: int) -> datetime:
    """Start of the N minute slot containing `ts` (the grid is anchored at midnight; 09:15 is on it for 3, 5 and 15)."""
    ts = ts.replace(second=0, microsecond=0)
    since_midnight = ts.hour * 60 + ts.minute
    return ts - timedelta(minutes=since_midnight % minutes)


class BarBuilder:
    def __init__(self, minutes: int = 3):
        self.minutes = minutes
        self.bars: list[dict] = []          # completed bars, oldest first
        self.forming: Optional[dict] = None

    @property
    def count(self) -> int:
        return len(self.bars)

    def seed(self, one_minute: Iterable[dict], now: Optional[datetime] = None) -> int:
        """Replace the history with bars aggregated from 1 minute bars (dicts with timestamp/open/high/low/close/volume)."""
        now = now or market_hours.now_ist_naive()
        grouped: dict[datetime, dict] = {}
        for row in sorted(one_minute, key=lambda r: pd.Timestamp(r["timestamp"])):
            ts = pd.Timestamp(row["timestamp"]).to_pydatetime()
            if not (market_hours.MARKET_OPEN <= ts.time() < market_hours.MARKET_CLOSE):
                continue
            slot = slot_start(ts, self.minutes)
            bar = grouped.get(slot)
            if bar is None:
                grouped[slot] = {"timestamp": slot, "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]),
                                 "close": float(row["close"]), "volume": int(row.get("volume", 0) or 0)}
            else:
                bar["high"] = max(bar["high"], float(row["high"]))
                bar["low"] = min(bar["low"], float(row["low"]))
                bar["close"] = float(row["close"])
                bar["volume"] += int(row.get("volume", 0) or 0)
        completed, forming = [], None
        for slot in sorted(grouped):
            if slot + timedelta(minutes=self.minutes) <= now:
                completed.append(grouped[slot])
            else:
                forming = grouped[slot]
        self.bars, self.forming = completed, forming
        return len(completed)

    def update(self, price: float, now: Optional[datetime] = None) -> bool:
        """Fold one live price in. Returns True when this tick completed a bar."""
        now = now or market_hours.now_ist_naive()
        if price is None or price <= 0 or not market_hours.is_market_open(now):
            return False
        slot = slot_start(now, self.minutes)
        completed = False
        if self.forming is not None and self.forming["timestamp"] < slot:
            self.bars.append(self.forming)
            self.forming = None
            completed = True
        if self.forming is None:
            self.forming = {"timestamp": slot, "open": price, "high": price, "low": price, "close": price, "volume": 0}
        else:
            self.forming["high"] = max(self.forming["high"], price)
            self.forming["low"] = min(self.forming["low"], price)
            self.forming["close"] = price
        return completed

    def completed_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.bars)
