#!/usr/bin/env python3
"""What would each liquidity threshold have saved? Reads closed trades from trades.db.

Usage: python scripts/liquidity_analysis.py [path/to/trades.db]

Uses the entry_spread_pct / option_volume / option_oi / entry-premium columns logged on each
position. Rows without the field (older trades, or the feed gave none) are counted as "no data"
and never as skipped. Quarantined/archived trades are ignored. "Saved" is the net P&L you
avoid: positive means skipping those trades would have helped.
"""
import os
import sqlite3
import sys

SPREAD = [3, 5, 8, 10, 15, 20, 25]
VOLUME = [10, 50, 100, 250, 500, 1000]
OI = [100, 500, 1000, 5000, 10000, 25000]
PREMIUM = [2, 3, 5, 8, 10, 15]


def load(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(positions)")}
    need = {"entry_spread_pct", "option_volume", "option_oi", "net_pnl", "option_entry"}
    if not need <= cols:
        sys.exit(f"positions table lacks liquidity columns {sorted(need - cols)}; deploy PR #21 first")
    where = "status='CLOSED'"
    if "quarantine_reason" in cols:
        where += " AND quarantine_reason IS NULL"
    if "archived_at" in cols:
        where += " AND archived_at IS NULL"
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM positions WHERE {where}")]
    conn.close()
    return rows


def sweep(rows, label, key, thresholds, skip_if):
    known = [r for r in rows if r.get(key) is not None]
    print(f"\n{label}: {len(known)} of {len(rows)} trades have data")
    if not known:
        return
    print(f"  {'threshold':>10} {'skipped':>8} {'wins':>5} {'losses':>7} {'skipped net':>12} {'kept net':>10}")
    for t in thresholds:
        skipped = [r for r in known if skip_if(r[key], t)]
        kept = [r for r in rows if r not in skipped]
        net = lambda xs: sum(r.get("net_pnl") or 0 for r in xs)
        wins = sum(1 for r in skipped if (r.get("net_pnl") or 0) > 0)
        print(f"  {t:>10g} {len(skipped):>8} {wins:>5} {len(skipped) - wins:>7} "
              f"{net(skipped):>12.0f} {net(kept):>10.0f}")


def main(db_path):
    rows = load(db_path)
    total = sum(r.get("net_pnl") or 0 for r in rows)
    print(f"{len(rows)} closed trades, net P&L {total:.0f}")
    if len(rows) < 30:
        print("WARNING: fewer than 30 trades; treat every number below as noise.")
    sweep(rows, "Skip if spread % >", "entry_spread_pct", SPREAD, lambda v, t: v > t)
    sweep(rows, "Skip if volume <", "option_volume", VOLUME, lambda v, t: v < t)
    sweep(rows, "Skip if open interest <", "option_oi", OI, lambda v, t: v < t)
    sweep(rows, "Skip if entry premium <", "option_entry", PREMIUM, lambda v, t: v < t)
    print("\n'skipped net' negative = skipping would have saved that much. Pick thresholds, then set "
          "LIQ_MAX_SPREAD_PCT / LIQ_MIN_VOLUME / LIQ_MIN_OI / LIQ_MIN_PREMIUM and LIQ_FILTER_ENABLED=1.")


if __name__ == "__main__":
    default = os.path.join(os.path.dirname(__file__), "..", "data", "trades.db")
    main(sys.argv[1] if len(sys.argv) > 1 else default)
