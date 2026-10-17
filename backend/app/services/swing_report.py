"""Statistics for closed swing trades: used by the replay script and its tests. No I/O."""
from __future__ import annotations

import math
import random
from typing import Optional

MIN_TRADES = 100  # below this the numbers are anecdotes; the report says so


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a win rate (as fractions)."""
    if n <= 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_mean_ci(values: list[float], iterations: int = 2000, seed: int = 7) -> tuple[float, float]:
    """95% percentile bootstrap interval for the mean (seeded, so a report is repeatable)."""
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iterations))
    return means[int(0.025 * iterations)], means[int(0.975 * iterations) - 1]


def max_drawdown(pnls_in_close_order: list[float], start_capital: float) -> float:
    """Largest peak-to-trough fall of the closed-trade equity curve, as a fraction of the peak."""
    equity, peak, worst = start_capital, start_capital, 0.0
    for p in pnls_in_close_order:
        equity += p
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return worst


def summarise(trades: list[dict], start_capital: float = 1_000_000.0) -> dict:
    """Metrics for closed trades (dicts from the engine: net_pnl, return_pct, r_multiple, hold_days, exit_reason, closed_day)."""
    closed = sorted((t for t in trades if t.get("status") == "CLOSED"), key=lambda t: (t["closed_day"], t["id"]))
    n = len(closed)
    out: dict = {"trades": n, "enough_trades": n >= MIN_TRADES}
    if n == 0:
        return out
    net = [t["net_pnl"] for t in closed]
    rs = [t.get("r_multiple", 0.0) for t in closed]
    rets = [t.get("return_pct", 0.0) for t in closed]
    wins = sum(1 for x in net if x > 0)
    gross_win = sum(x for x in net if x > 0)
    gross_loss = -sum(x for x in net if x < 0)
    lo, hi = wilson_interval(wins, n)
    r_lo, r_hi = bootstrap_mean_ci(rs)
    reasons: dict[str, int] = {}
    for t in closed:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    out.update({
        "net_pnl": round(sum(net), 2), "total_charges": round(sum(t.get("charges", 0.0) for t in closed), 2),
        "win_rate_pct": round(wins / n * 100, 1), "win_rate_ci95_pct": [round(lo * 100, 1), round(hi * 100, 1)],
        "avg_return_pct": round(sum(rets) / n, 3), "expectancy_r": round(sum(rs) / n, 3),
        "expectancy_r_ci95": [round(r_lo, 3), round(r_hi, 3)],
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "avg_hold_days": round(sum(t.get("hold_days", 0) for t in closed) / n, 1),
        "max_drawdown_pct": round(max_drawdown(net, start_capital) * 100, 2),
        "exit_reasons": dict(sorted(reasons.items())),
    })
    out["verdict_note"] = ("" if out["enough_trades"] else f"only {n} trades (< {MIN_TRADES}): treat as a hypothesis, not a result")
    return out


def split_halves(trades: list[dict], split_day: Optional[str]) -> tuple[list[dict], list[dict]]:
    """Trades opened before / on-or-after ``split_day`` (walk-forward check). No split day: the median opening day."""
    opened = sorted(t["opened_day"] for t in trades if t.get("opened_day"))
    if not opened:
        return [], []
    cut = split_day or opened[len(opened) // 2]
    return ([t for t in trades if t.get("opened_day") and t["opened_day"] < cut],
            [t for t in trades if t.get("opened_day") and t["opened_day"] >= cut])
