"""Deep performance statistics over closed paper trades, joined with MFE / MAE telemetry.

All numbers are net of charges unless stated. Quarantined rows are skipped. "R" is net P&L divided by the capital at
risk at entry (entry-to-stop distance x initial quantity); it is None for trades without a measurable stop.

The report answers: how much does each setup earn per trade (expectancy), how fast does it lose (drawdown, loss
streaks), how much of the available move does it keep (capture = realised / MFE), how far does it run against us
before working (MAE) and what do slippage and charges take.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Optional

from app.services.paper_models import _parse_iso


def _outcome(p) -> float:
    if getattr(p, "net_pnl", 0.0) or getattr(p, "total_charges", 0.0):
        return float(p.net_pnl)
    return float(p.pnl_rupees)


def _r(p) -> Optional[float]:
    qty = p.initial_quantity or p.quantity
    stop = getattr(p, "initial_option_sl", None) or p.option_sl
    risk = (p.option_entry - stop) * qty
    return _outcome(p) / risk if risk > 0 else None


def _minutes_held(p) -> Optional[float]:
    a, b = _parse_iso(p.entry_datetime), _parse_iso(p.exit_datetime)
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds() / 60.0)


def _bucket(trades: list, excursions: dict[str, dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    pnls = [_outcome(p) for p in trades]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    rs = [r for r in (_r(p) for p in trades) if r is not None]
    held = [m for m in (_minutes_held(p) for p in trades) if m is not None]

    ordered = sorted(trades, key=lambda p: str(p.exit_datetime or p.entry_datetime or ""))
    equity, peak, max_dd, run_loss, max_run_loss = 0.0, 0.0, 0.0, 0, 0
    for p in ordered:
        v = _outcome(p)
        equity += v
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        run_loss = run_loss + 1 if v < 0 else 0
        max_run_loss = max(max_run_loss, run_loss)

    mean = sum(pnls) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in pnls) / (n - 1)) if n > 1 else 0.0

    exc = [excursions[p.id] for p in trades if p.id in excursions]
    mfes = [e["mfe"] for e in exc]
    maes = [e["mae"] for e in exc]
    capture = [(_outcome(p) / excursions[p.id]["mfe"]) for p in trades
               if p.id in excursions and excursions[p.id]["mfe"] > 0 and _outcome(p) > 0]
    # winners that were deeply under water first, and losers that were once comfortably green
    pain = [e["mae"] for p in trades if (e := excursions.get(p.id)) and _outcome(p) > 0]
    gave_back = [p for p in trades if (e := excursions.get(p.id)) and _outcome(p) < 0 and e["mfe"] > 0]

    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n * 100, 1),
        "net_pnl": round(sum(pnls), 2),
        "gross_pnl": round(sum(float(getattr(p, "gross_pnl", 0.0) or p.pnl_rupees) for p in trades), 2),
        "charges": round(sum(float(getattr(p, "total_charges", 0.0)) for p in trades), 2),
        "slippage_cost": round(sum(float(getattr(p, "total_slippage_cost", 0.0)) for p in trades), 2),
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "expectancy": round(mean, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "payoff_ratio": round((gross_win / len(wins)) / (gross_loss / len(losses)), 2) if wins and losses else None,
        "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
        "r_trades": len(rs),
        "std_dev": round(std, 2),
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "max_drawdown": round(max_dd, 2),
        "max_consecutive_losses": max_run_loss,
        "avg_minutes_held": round(sum(held) / len(held), 1) if held else None,
        "excursion_trades": len(exc),
        "avg_mfe": round(sum(mfes) / len(mfes), 2) if mfes else None,
        "avg_mae": round(sum(maes) / len(maes), 2) if maes else None,
        "avg_capture_pct": round(sum(capture) / len(capture) * 100, 1) if capture else None,
        "avg_winner_mae": round(sum(pain) / len(pain), 2) if pain else None,
        "losers_that_were_green": len(gave_back),
    }


def build_report(closed_trades: Iterable, excursions: list[dict], book: Optional[str] = None) -> dict:
    """Overall, per-setup, per-symbol, per-hour, per-exit-reason and equity-curve statistics."""
    trades = [p for p in closed_trades
              if not p.quarantine_reason and (book is None or getattr(p, "feed_mode", "demo") == book)]
    exc = {e["position_id"]: e for e in excursions}

    by_setup: dict[str, list] = defaultdict(list)
    by_symbol: dict[str, list] = defaultdict(list)
    by_hour: dict[str, list] = defaultdict(list)
    by_side: dict[str, list] = defaultdict(list)
    by_exit: dict[str, list] = defaultdict(list)
    for p in trades:
        by_setup[p.setup_type].append(p)
        by_symbol[p.symbol].append(p)
        by_side[p.option_type].append(p)
        ent = _parse_iso(p.entry_datetime)
        by_hour[f"{ent.hour:02d}:00" if ent else "unknown"].append(p)
        reason = (p.exit_reason or p.status or "unknown").split(" (")[0].split(":")[0].strip()[:40] or "unknown"
        by_exit[reason].append(p)

    curve, cum = [], 0.0
    for p in sorted(trades, key=lambda x: str(x.exit_datetime or x.entry_datetime or "")):
        cum += _outcome(p)
        curve.append({"t": str(p.exit_datetime or p.entry_datetime or ""), "equity": round(cum, 2), "id": p.id})

    def pack(groups: dict[str, list]) -> list[dict]:
        rows = [{"key": k, **_bucket(v, exc)} for k, v in groups.items()]
        rows.sort(key=lambda r: r["net_pnl"], reverse=True)
        return rows

    return {
        "book": book or "all",
        "overall": _bucket(trades, exc),
        "by_setup": pack(by_setup),
        "by_symbol": pack(by_symbol),
        "by_side": pack(by_side),
        "by_entry_hour": sorted(pack(by_hour), key=lambda r: r["key"]),
        "by_exit_reason": pack(by_exit),
        "equity_curve": curve[-1000:],
    }
