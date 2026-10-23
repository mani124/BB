"""Read-only analytics over closed paper trades and open positions, for the dashboard's Performance, Execution and Risk panels.

Everything is computed from data the engine already keeps; nothing here writes or changes trading behaviour. Per-bucket
maths is shared with ``performance_report`` (imported, not copied). Quarantined trades are excluded and counted.
JSON output never contains NaN or Infinity (see ``clean``).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable, Optional

from app.services import market_hours
from app.services.paper_models import _parse_iso
from app.services.performance_report import _bucket, _minutes_held, _outcome, _r
from app.services.strategy_engine import pool_of

LOW_SAMPLE = 20
MAX_POINTS = 3000
GROUPS = ("setup", "symbol", "side", "hour", "weekday", "exit_reason")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
OPTIONAL_FIELDS = ("entry_spread_pct", "option_volume", "option_oi", "entry_delay_s", "entry_bid", "charges_breakdown", "initial_option_sl")


def clean(x: Any) -> Any:
    """Recursively replaces NaN and +-Infinity with None so the response is valid JSON."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def now_iso() -> str:
    return market_hours.now_ist().isoformat()


# ---- common helpers ----------------------------------------------------------------------------------------------

def parse_range(from_: Optional[str], to: Optional[str]) -> tuple[Optional[date], Optional[date]]:
    """IST dates, inclusive. Raises ValueError on a bad date or a reversed range."""
    a = date.fromisoformat(from_) if from_ else None
    b = date.fromisoformat(to) if to else None
    if a and b and b < a:
        raise ValueError("'to' must not be before 'from'")
    return a, b


def _ist(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.astimezone(market_hours.IST) if dt else None


def trade_time(p) -> Optional[datetime]:
    """When the trade closed (IST), falling back to its entry."""
    return _ist(_parse_iso(getattr(p, "exit_datetime", None)) or _parse_iso(getattr(p, "entry_datetime", None)))


def entry_time(p) -> Optional[datetime]:
    return _ist(_parse_iso(getattr(p, "entry_datetime", None)))


def filter_trades(trades: Iterable, *, rng: tuple[Optional[date], Optional[date]] = (None, None), book: Optional[str] = None,
                  setup: Optional[str] = None, side: Optional[str] = None) -> tuple[list, int]:
    """Returns (kept, excluded_count). ``book`` None or 'all' keeps every feed mode; otherwise it matches ``feed_mode``."""
    lo, hi = rng
    kept, excluded = [], 0
    for p in trades:
        when = trade_time(p)
        if lo or hi:
            if when is None:
                continue
            d = when.date()
            if (lo and d < lo) or (hi and d > hi):
                continue
        if book not in (None, "all") and getattr(p, "feed_mode", "demo") != book:
            continue
        if setup and setup.lower() not in str(p.setup_type).lower():
            continue
        if side and p.option_type != side:
            continue
        if getattr(p, "quarantine_reason", None):
            excluded += 1
            continue
        kept.append(p)
    return kept, excluded


def _sorted(trades: list) -> list:
    return sorted(trades, key=lambda p: (trade_time(p) or datetime.min.replace(tzinfo=market_hours.IST)))


def _percentile(sorted_vals: list[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * q
    f = math.floor(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _hist(values: list[float], bins: int) -> list[dict]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [{"lo": round(lo, 2), "hi": round(hi, 2), "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - lo) / width), bins - 1)] += 1
    return [{"lo": round(lo + i * width, 2), "hi": round(lo + (i + 1) * width, 2), "count": c} for i, c in enumerate(counts)]


# ---- equity ------------------------------------------------------------------------------------------------------

def equity_report(trades: list, excluded: int = 0) -> dict:
    ordered = _sorted(trades)
    points: list[dict] = []
    equity = peak = 0.0
    day_key, day_pnl = None, 0.0
    episodes: list[dict] = []
    cur: Optional[dict] = None
    peak_t: Optional[str] = None
    max_dd = 0.0
    for p in ordered:
        when = trade_time(p)
        t = when.isoformat() if when else ""
        v = _outcome(p)
        d = when.date() if when else None
        if d != day_key:
            day_key, day_pnl = d, 0.0
        day_pnl += v
        equity += v
        if peak_t is None:
            peak_t = t
        if equity >= peak:
            if cur is not None:
                cur["end"] = t
                episodes.append(cur)
                cur = None
            peak, peak_t = equity, t
        else:
            if cur is None:
                cur = {"start": peak_t, "trough": t, "end": None, "depth": 0.0, "_trough_eq": equity, "_peak": peak}
            if equity < cur["_trough_eq"]:
                cur["_trough_eq"], cur["trough"] = equity, t
            cur["depth"] = round(cur["_peak"] - cur["_trough_eq"], 2)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        points.append({"t": t, "equity": round(equity, 2), "day_pnl": round(day_pnl, 2), "drawdown": round(dd, 2)})
    if cur is not None:
        episodes.append(cur)

    def days(e: dict) -> int:
        a = _parse_iso(e["start"])
        b = _parse_iso(e["end"]) if e["end"] else (_parse_iso(points[-1]["t"]) if points else None)
        return max(0, (_ist(b).date() - _ist(a).date()).days) if a and b else 0

    longest = max((days(e) for e in episodes), default=0)
    top = sorted(episodes, key=lambda e: e["depth"], reverse=True)[:5]
    top = [{k: v for k, v in e.items() if not k.startswith("_")} for e in top]
    return clean({
        "points": points[-MAX_POINTS:],
        "summary": {
            "net": round(equity, 2),
            "max_drawdown": round(max_dd, 2),
            "current_drawdown": round(peak - equity, 2) if points else 0.0,
            "longest_drawdown_days": longest,
            "drawdowns": top,
        },
        "generated_at": now_iso(),
        "excluded": excluded,
    })


# ---- attribution -------------------------------------------------------------------------------------------------

def _exit_reason(p) -> str:
    return (p.exit_reason or p.status or "unknown").split(" (")[0].split(":")[0].strip()[:40] or "unknown"


def _key_of(p, group: str) -> str:
    if group == "setup":
        return str(p.setup_type)
    if group == "symbol":
        return p.symbol
    if group == "side":
        return p.option_type
    if group == "exit_reason":
        return _exit_reason(p)
    ent = entry_time(p)
    if group == "hour":
        return f"{ent.hour:02d}:00" if ent else "unknown"
    if group == "weekday":
        return WEEKDAYS[ent.weekday()] if ent else "unknown"
    raise ValueError(f"unknown group {group}")


def attribution_report(trades: list, excursions: list[dict], group: str = "setup", excluded: int = 0) -> dict:
    if group not in GROUPS:
        raise ValueError(f"group must be one of {', '.join(GROUPS)}")
    exc = {e["position_id"]: e for e in excursions}
    groups: dict[str, list] = defaultdict(list)
    for p in trades:
        groups[_key_of(p, group)].append(p)
    buckets = []
    for key, rows in groups.items():
        b = _bucket(rows, exc)
        gross = float(b.get("gross_pnl", 0.0))
        drag = (float(b.get("charges", 0.0)) + float(b.get("slippage_cost", 0.0))) / abs(gross) * 100 if gross else None
        buckets.append({"key": key, **b, "cost_drag_pct": round(drag, 1) if drag is not None else None,
                        "low_sample": b["trades"] < LOW_SAMPLE})
    if group == "hour":
        buckets.sort(key=lambda r: r["key"])
    elif group == "weekday":
        buckets.sort(key=lambda r: WEEKDAYS.index(r["key"]) if r["key"] in WEEKDAYS else 99)
    else:
        buckets.sort(key=lambda r: r["net_pnl"], reverse=True)
    overall = _bucket(trades, exc)
    overall["low_sample"] = overall["trades"] < LOW_SAMPLE
    return clean({"group": group, "buckets": buckets, "overall": overall, "generated_at": now_iso(), "excluded": excluded})


# ---- distribution ------------------------------------------------------------------------------------------------

def distribution_report(trades: list, excursions: list[dict], bins: int = 20, excluded: int = 0) -> dict:
    bins = max(1, min(int(bins), 60))
    pnls = [_outcome(p) for p in trades]
    rs = [r for r in (_r(p) for p in trades) if r is not None]
    held = [m for m in (_minutes_held(p) for p in trades) if m is not None]
    exc = {e["position_id"]: e for e in excursions}
    pts = [{"id": p.id, "mfe": exc[p.id]["mfe"], "mae": exc[p.id]["mae"], "final": round(_outcome(p), 2)} for p in trades if p.id in exc]

    def med(vals: list[float]) -> dict:
        s = sorted(vals)
        return {"p10": _percentile(s, 0.1), "p50": _percentile(s, 0.5), "p90": _percentile(s, 0.9)}

    return clean({
        "pnl": _hist(pnls, bins), "r": _hist(rs, bins), "hold_minutes": _hist(held, bins),
        "mfe_mae": pts[-2000:],
        "medians": {"pnl": med(pnls), "r": med(rs), "hold_minutes": med(held)},
        "generated_at": now_iso(), "excluded": excluded,
    })


# ---- execution ---------------------------------------------------------------------------------------------------

CHARGE_PARTS = ("brokerage", "stt", "exchange_fee", "sebi_fee", "stamp_duty", "gst")
SPREAD_BUCKETS = ((0.0, 1.0, "<1%"), (1.0, 2.0, "1-2%"), (2.0, 3.0, "2-3%"), (3.0, math.inf, ">3%"))


def _avg(vals: list[float]) -> Optional[float]:
    return round(sum(vals) / len(vals), 4) if vals else None


def execution_report(trades: list, excluded: int = 0) -> dict:
    entry = [round(float(p.entry_slippage), 4) for p in trades]
    exit_ = [round(float(p.exit_slippage), 4) for p in trades]

    def slip_by(keyfn) -> list[dict]:
        g: dict[str, list] = defaultdict(list)
        for p in trades:
            g[keyfn(p)].append(p)
        rows = [{"key": k, "trades": len(v), "entry_avg": _avg([float(p.entry_slippage) for p in v]),
                 "exit_avg": _avg([float(p.exit_slippage) for p in v]),
                 "total_cost": round(sum(float(p.total_slippage_cost) for p in v), 2)} for k, v in g.items()]
        return sorted(rows, key=lambda r: r["key"])

    spread_pts = [{"spread_pct": round(float(p.entry_spread_pct), 3), "slippage": round(float(p.entry_slippage), 4)}
                  for p in trades if p.entry_spread_pct is not None]
    spread_buckets = []
    for lo, hi, label in SPREAD_BUCKETS:
        rows = [q for q in spread_pts if lo <= q["spread_pct"] < hi]
        if rows:
            spread_buckets.append({"label": label, "trades": len(rows), "avg_slippage": _avg([q["slippage"] for q in rows])})

    with_vol = sorted([p for p in trades if p.option_volume is not None], key=lambda p: p.option_volume)
    quartiles = []
    if with_vol:
        n = len(with_vol)
        for i in range(4):
            chunk = with_vol[i * n // 4:(i + 1) * n // 4] if n >= 4 else (with_vol if i == 0 else [])
            if chunk:
                quartiles.append({"q": i + 1, "volume_lo": chunk[0].option_volume, "volume_hi": chunk[-1].option_volume,
                                  "trades": len(chunk), "avg_slippage": _avg([float(p.entry_slippage) for p in chunk]),
                                  "net_pnl": round(sum(_outcome(p) for p in chunk), 2)})

    totals = {k: 0.0 for k in CHARGE_PARTS}
    by_setup: dict[str, dict] = {}
    for p in trades:
        bd = p.charges_breakdown or {}
        row = by_setup.setdefault(str(p.setup_type), {"key": str(p.setup_type), **{k: 0.0 for k in CHARGE_PARTS}, "total": 0.0, "trades": 0})
        row["trades"] += 1
        for k in CHARGE_PARTS:
            v = float(bd.get(k, 0.0) or 0.0)
            totals[k] += v
            row[k] += v
        row["total"] += float(p.total_charges or 0.0)
    for row in by_setup.values():
        for k in (*CHARGE_PARTS, "total"):
            row[k] = round(row[k], 2)

    not_recorded = [f for f in OPTIONAL_FIELDS if trades and all(getattr(p, f, None) in (None, {}) for p in trades)]
    return clean({
        "slippage": {
            "entry": entry[-2000:], "exit": exit_[-2000:],
            "by_setup": slip_by(lambda p: str(p.setup_type)),
            "by_hour": slip_by(lambda p: (f"{entry_time(p).hour:02d}:00" if entry_time(p) else "unknown")),
        },
        "spread": {"points": spread_pts[-2000:], "buckets": spread_buckets},
        "liquidity": {"quartiles": quartiles},
        "charges": {"totals": {k: round(v, 2) for k, v in totals.items()}, "by_setup": sorted(by_setup.values(), key=lambda r: r["key"])},
        "not_recorded": not_recorded,
        "generated_at": now_iso(), "excluded": excluded,
    })


# ---- risk --------------------------------------------------------------------------------------------------------

OPEN_STATUSES = ("OPEN", "TARGET_1")
MAX_OPEN_KEY = "max_open_positions"


def risk_snapshot(positions: Iterable, settings: Any = None) -> dict:
    rows = []
    for p in positions:
        if p.status not in OPEN_STATUSES:
            continue
        qty = int(p.quantity)
        risk = max(0.0, qty * (float(p.option_entry) - float(p.option_sl)))
        last = float(p.current_option_price)
        rows.append({
            "id": p.id, "symbol": p.symbol, "strike_symbol": p.strike_symbol, "side": p.option_type, "setup": str(p.setup_type),
            "pool": pool_of(p.setup_type), "qty": qty, "entry": float(p.option_entry), "stop": float(p.option_sl),
            "risk_rupees": round(risk, 2), "notional": round(qty * float(p.option_entry), 2),
            "distance_pct": round((last - float(p.option_sl)) / last * 100, 2) if last > 0 else None,
            "t1": float(p.option_target_1),
        })

    def group(field: str) -> list[dict]:
        g: dict[str, dict] = {}
        for r in rows:
            row = g.setdefault(r[field], {"key": r[field], "count": 0, "risk_rupees": 0.0, "notional": 0.0})
            row["count"] += 1
            row["risk_rupees"] = round(row["risk_rupees"] + r["risk_rupees"], 2)
            row["notional"] = round(row["notional"] + r["notional"], 2)
        return sorted(g.values(), key=lambda r: r["risk_rupees"], reverse=True)

    max_open = None
    if settings is not None:
        try:
            max_open = settings.get(MAX_OPEN_KEY)
        except Exception:
            max_open = None
    return clean({
        "open": rows,
        "totals": {"risk_rupees": round(sum(r["risk_rupees"] for r in rows), 2), "notional": round(sum(r["notional"] for r in rows), 2),
                   "count": len(rows), "max_open": max_open, "max_open_key": MAX_OPEN_KEY},
        "by_underlying": group("symbol"), "by_side": group("side"), "by_pool": group("pool"), "by_setup": group("setup"),
        "generated_at": now_iso(),
    })
