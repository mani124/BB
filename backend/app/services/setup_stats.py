"""Per-setup, per-day performance stats over closed paper trades.

Quarantined rows are skipped (archived rows are never loaded into the portfolio). "R" is
net P&L divided by the capital at risk at entry (entry-to-stop distance x initial quantity).
"""
from typing import Iterable, Optional
from pydantic import BaseModel
from app.services.paper_models import _parse_iso

class SetupDayStats(BaseModel):
    setup_type: str
    date: str  # IST exit date, or "ALL" for the per-setup total
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    avg_r: Optional[float] = None  # None when no trade had a measurable stop distance
    # Trades that went into avg_r. After Target 1 the stop moves to entry, so those trades have no
    # measurable initial risk and are left out: avg_r only covers trades stopped or exited before that.
    r_trades: int = 0
    gross_pnl: float = 0.0
    total_slippage_cost: float = 0.0
    total_charges: float = 0.0
    net_pnl: float = 0.0

def _trade_r(p) -> Optional[float]:
    qty = p.initial_quantity or p.quantity
    risk = (p.option_entry - p.option_sl) * qty
    if risk <= 0:
        return None
    return p.net_pnl / risk

def compute_setup_stats(closed_trades: Iterable) -> list[SetupDayStats]:
    acc: dict[tuple[str, str], dict] = {}
    for p in closed_trades:
        if p.quarantine_reason:
            continue
        stamp = _parse_iso(p.exit_datetime) or _parse_iso(p.entry_datetime)
        day = stamp.date().isoformat() if stamp else "unknown"
        r = _trade_r(p)
        for key in ((p.setup_type, day), (p.setup_type, "ALL")):
            a = acc.setdefault(key, dict(trades=0, wins=0, rs=[], gross=0.0, slip=0.0, chg=0.0, net=0.0))
            a["trades"] += 1
            a["wins"] += 1 if p.net_pnl > 0 else 0
            if r is not None:
                a["rs"].append(r)
            a["gross"] += p.gross_pnl or p.pnl_rupees
            a["slip"] += p.total_slippage_cost
            a["chg"] += p.total_charges
            a["net"] += p.net_pnl
    rows = [
        SetupDayStats(
            setup_type=s, date=d, trades=a["trades"], wins=a["wins"],
            win_rate=round(a["wins"] / a["trades"] * 100, 1),
            avg_r=round(sum(a["rs"]) / len(a["rs"]), 2) if a["rs"] else None, r_trades=len(a["rs"]),
            gross_pnl=round(a["gross"], 2), total_slippage_cost=round(a["slip"], 2),
            total_charges=round(a["chg"], 2), net_pnl=round(a["net"], 2),
        )
        for (s, d), a in acc.items()
    ]
    # per setup: the ALL total first, then days newest first
    rows.sort(key=lambda r: (r.setup_type, r.date != "ALL", _neg(r.date)))
    return rows

def _neg(date: str) -> str:
    return "".join(chr(255 - ord(c)) for c in date)
