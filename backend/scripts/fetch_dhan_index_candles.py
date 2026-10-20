"""Download historical 1 minute index candles from Dhan and write 1m and 3m CSVs for offline replays.

Usage (from backend/), with your own Dhan session in the environment (never pass the token on the command line):
    export DHAN_CLIENT_ID=...   DHAN_ACCESS_TOKEN=...
    python -m scripts.fetch_dhan_index_candles --days 30 --out ../notes_tmp/dhan_candles

Why 1 minute: Dhan serves 1, 5, 15, 25 and 60 minute candles, not 3, so a 3 minute chart is built from the 1 minute
bars (bins start at 09:15 and run to 15:30). The token is read from the environment, sent only to Dhan's API and
never printed or written to disk. Needs a Dhan account with the Data API enabled.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

from app.services.dhan_client import DhanClient
from app.services.universe_manager import UniverseManager

CHUNK_DAYS = 7  # a week of 1 minute bars per request keeps each response small
SESSION_START, SESSION_END = "09:15", "15:29"


def to_3m(one_minute: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1 minute bars to 3 minute bars labelled by their start time (09:15, 09:18, ...)."""
    df = one_minute.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")
    df = df.between_time(SESSION_START, SESSION_END)
    agg = df.resample("3min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return agg.dropna(subset=["open"]).reset_index()


async def fetch_symbol(client: DhanClient, creds: tuple[str, str], inst, days: int) -> pd.DataFrame:
    end = datetime.now()
    parts = []
    start = end - timedelta(days=days)
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(days=CHUNK_DAYS), end)
        df = await client.fetch_intraday_candles(
            creds[0], creds[1], inst.security_id, inst.exchange_segment, inst.instrument_type, interval=1,
            from_date=cursor.strftime("%Y-%m-%d 09:15:00"), to_date=nxt.strftime("%Y-%m-%d 15:30:00"))
        if not df.empty:
            parts.append(df)
        cursor = nxt
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default="dhan_candles")
    ap.add_argument("--symbols", default="NIFTY 50,NIFTY BANK")
    args = ap.parse_args()
    client_id, token = os.environ.get("DHAN_CLIENT_ID", ""), os.environ.get("DHAN_ACCESS_TOKEN", "")
    if not client_id or not token:
        print("Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in the environment first.", file=sys.stderr)
        return 2
    wanted = {s.strip().upper() for s in args.symbols.split(",")}
    instruments = [i for i in UniverseManager.INDICES if i.symbol.upper() in wanted]
    os.makedirs(args.out, exist_ok=True)
    client = DhanClient()
    for inst in instruments:
        one = await fetch_symbol(client, (client_id, token), inst, args.days)
        if one.empty:
            print(f"{inst.symbol}: no candles returned (check the token, the Data API subscription and the date range)")
            continue
        safe = inst.symbol.replace(" ", "_")
        one.to_csv(os.path.join(args.out, f"{safe}_1m.csv"), index=False)
        three = to_3m(one)
        three.to_csv(os.path.join(args.out, f"{safe}_3m.csv"), index=False)
        print(f"{inst.symbol}: {len(one)} one-minute bars, {len(three)} three-minute bars, "
              f"{one.timestamp.min()} to {one.timestamp.max()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
