"""Cost view over closed paper trades: gross P&L, slippage, charges and net.

How to read the numbers (verified against paper_exits._finalize_closed_position):
  * gross_pnl is computed from the actual FILL prices, so slippage is already inside it.
    It is not subtracted a second time anywhere. net = gross - charges.
  * total_slippage_cost (Rs) = entry slippage x initial qty + slippage on any Target 1 partial
    + exit slippage x runner qty. Entry slippage is fill - signal price, clamped at 0 (a better
    fill is not credited). Exit slippage is signed: positive = filled worse than the level,
    negative = price improvement.
  * gross_before_slippage = gross + slippage is what the trade would have made at the
    intended prices, and so shows what slippage alone cost.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from pydantic import BaseModel

# (upper bound exclusive, label) on the option entry premium in Rs.
PREMIUM_BUCKETS: list[tuple[float, str]] = [
    (50.0, "Under 50"),
    (100.0, "50 - 100"),
    (200.0, "100 - 200"),
    (400.0, "200 - 400"),
    (float("inf"), "400 and above"),
]


class CostTotals(BaseModel):
    trades: int = 0
    gross_pnl: float = 0.0
    slippage: float = 0.0
    charges: float = 0.0
    net_pnl: float = 0.0
    gross_before_slippage: float = 0.0
    avg_slippage_per_trade: float = 0.0


class CostGroup(CostTotals):
    key: str = ""


class CostTrade(BaseModel):
    id: str
    symbol: str
    setup_type: str
    date: str
    exit_time: Optional[str] = None
    option_entry: float = 0.0
    gross_pnl: float = 0.0
    slippage: float = 0.0
    charges: float = 0.0
    net_pnl: float = 0.0


class CostDay(CostTotals):
    date: str = ""


class CostReport(BaseModel):
    totals: CostTotals
    trades: list[CostTrade]
    by_day: list[CostDay]
    by_setup: list[CostGroup]
    by_symbol: list[CostGroup]
    by_premium: list[CostGroup]


def premium_bucket(premium: float) -> str:
    for upper, label in PREMIUM_BUCKETS:
        if premium < upper:
            return label
    return PREMIUM_BUCKETS[-1][1]


def _add(t: CostTotals, gross: float, slip: float, charges: float, net: float) -> None:
    t.trades += 1
    t.gross_pnl += gross
    t.slippage += slip
    t.charges += charges
    t.net_pnl += net


def _finish(t: CostTotals) -> None:
    t.gross_pnl = round(t.gross_pnl, 2)
    t.slippage = round(t.slippage, 2)
    t.charges = round(t.charges, 2)
    t.net_pnl = round(t.net_pnl, 2)
    t.gross_before_slippage = round(t.gross_pnl + t.slippage, 2)
    t.avg_slippage_per_trade = round(t.slippage / t.trades, 2) if t.trades else 0.0


def _setup_key(raw: Optional[str]) -> str:
    m = re.search(r"SETUP[_ ]?(\d)", (raw or "").upper())
    return f"Setup {m.group(1)}" if m else (raw or "unknown")


def _day_of(p) -> str:
    stamp = getattr(p, "exit_datetime", None) or getattr(p, "entry_datetime", None) or ""
    return stamp[:10] if len(stamp) >= 10 else "unknown"


def build_cost_report(closed: Iterable) -> CostReport:
    """Quarantined trades are skipped, matching every other performance figure."""
    totals = CostTotals()
    trades: list[CostTrade] = []
    days: dict[str, CostDay] = {}
    groups: dict[str, dict[str, CostGroup]] = {"setup": {}, "symbol": {}, "premium": {}}

    for p in closed:
        if getattr(p, "quarantine_reason", None):
            continue
        gross = float(getattr(p, "gross_pnl", 0.0) or p.pnl_rupees or 0.0)
        slip = float(getattr(p, "total_slippage_cost", 0.0) or 0.0)
        charges = float(getattr(p, "total_charges", 0.0) or 0.0)
        net = float(getattr(p, "net_pnl", 0.0) or 0.0)
        day = _day_of(p)
        entry = float(p.option_entry or 0.0)
        _add(totals, gross, slip, charges, net)
        d = days.setdefault(day, CostDay(date=day))
        _add(d, gross, slip, charges, net)
        for kind, key in (("setup", _setup_key(p.setup_type)), ("symbol", p.symbol), ("premium", premium_bucket(entry))):
            g = groups[kind].setdefault(key, CostGroup(key=key))
            _add(g, gross, slip, charges, net)
        trades.append(CostTrade(
            id=p.id, symbol=p.symbol, setup_type=p.setup_type or "unknown", date=day,
            exit_time=getattr(p, "exit_time", None), option_entry=round(entry, 2),
            gross_pnl=round(gross, 2), slippage=round(slip, 2), charges=round(charges, 2), net_pnl=round(net, 2),
        ))

    for t in [totals, *days.values(), *(g for m in groups.values() for g in m.values())]:
        _finish(t)

    by_cost = lambda g: -(g.slippage + g.charges)  # noqa: E731 - biggest cost first
    bucket_order = {label: i for i, (_, label) in enumerate(PREMIUM_BUCKETS)}
    return CostReport(
        totals=totals,
        trades=sorted(trades, key=lambda t: (t.date, t.exit_time or ""), reverse=True),
        by_day=sorted(days.values(), key=lambda d: d.date, reverse=True),
        by_setup=sorted(groups["setup"].values(), key=by_cost),
        by_symbol=sorted(groups["symbol"].values(), key=by_cost),
        by_premium=sorted(groups["premium"].values(), key=lambda g: bucket_order.get(g.key, 99)),
    )
