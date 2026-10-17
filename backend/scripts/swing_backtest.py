"""Replay the swing book (Setup 15) over daily bars with the production engine and print cost-inclusive statistics.

Usage (from backend/):
    python -m scripts.swing_backtest DATA_DIR [--from 2018-01-01] [--to 2026-10-16] [--split 2022-01-01]
        [--set swing_atr_period=3 --set swing_atr_mult=1.0 ...] [--no-stress] [--json out.json]

DATA_DIR holds one CSV per symbol (SYMBOL.csv) with columns date,open,high,low,close,volume, oldest first.
Rules (same as live): a signal on a close fills at the next open plus slippage, a gapped stop fills at the open, stops win
ties inside a bar, exits decided on a close fill at the next open. Signals only see bars up to the day being replayed.
The stress run repeats the replay at double the slippage; a setup whose expectancy does not survive it is not shippable.
Survivorship: the symbols in DATA_DIR are whatever you give it (today's F&O list is survivor-biased); say so in any write-up.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

import pandas as pd

from app.services.runtime_settings import RuntimeSettings
from app.services.swing_engine import SwingEngine
from app.services.swing_report import split_halves, summarise
from app.services.telemetry import Telemetry


def load_bars(data_dir: str) -> dict[str, pd.DataFrame]:
    bars = {}
    for name in sorted(os.listdir(data_dir)):
        if not name.lower().endswith(".csv"):
            continue
        df = pd.read_csv(os.path.join(data_dir, name))
        df.columns = [c.strip().lower() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        if "volume" not in df:
            df["volume"] = 0
        bars[name[:-4].upper()] = df[["date", "open", "high", "low", "close", "volume"]].dropna().sort_values("date").reset_index(drop=True)
    return bars


def replay(bars: dict[str, pd.DataFrame], overrides: dict, start: str | None = None, end: str | None = None) -> list[dict]:
    rt = RuntimeSettings(None)
    rt.set("swing_enabled", True)
    for key, value in overrides.items():
        rt.set(key, value, actor="backtest")
    engine = SwingEngine(None, rt, Telemetry(None, rt))
    days = sorted({d for df in bars.values() for d in df["date"]})
    days = [d for d in days if (start is None or d >= start) and (end is None or d <= end)]
    for d in days:
        engine.process_day(datetime.strptime(d, "%Y-%m-%d").date(), bars, scan=True)
    # anything still open is marked out at its last close so the statistics count it
    last = days[-1] if days else ""
    for pos in engine.store.positions():
        if pos["status"] == "OPEN":
            engine._close(pos, last, round(pos["last_close"] * (1 - engine._slip()), 2), "END_OF_TEST")
    return engine.positions("CLOSED")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--split", help="walk-forward cut date; default is the median opening day")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a swing_* runtime setting")
    ap.add_argument("--no-stress", action="store_true", help="skip the double-slippage run")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)
    overrides = dict(kv.split("=", 1) for kv in args.set)
    bars = load_bars(args.data_dir)
    if not bars:
        print("no CSV files found", file=sys.stderr)
        return 2
    trades = replay(bars, overrides, args.start, args.end)
    report = {"symbols": len(bars), "overrides": overrides, "all": summarise(trades)}
    first, second = split_halves(trades, args.split)
    report["first_half"], report["second_half"] = summarise(first), summarise(second)
    if not args.no_stress:
        slip = float(overrides.get("swing_slippage_bps", 10.0))
        stressed = replay(bars, {**overrides, "swing_slippage_bps": slip * 2}, args.start, args.end)
        report["double_slippage"] = summarise(stressed)
    text = json.dumps(report, indent=2)
    print(text)
    if args.json_out:
        with open(args.json_out, "w") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
