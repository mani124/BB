"""Delete every Setup 5 trade, and the records that belong to those trades, from the paper journal.

Usage (from backend/), with the service STOPPED (a running engine keeps trades in memory and would write them back):
    python -m scripts.purge_setup5 --db data/trades.db                 # dry run: counts only, changes nothing
    python -m scripts.purge_setup5 --db data/trades.db --yes           # backs the database up, then deletes

What goes: the positions (setup_type "Setup 5..."), their stored candles, excursions, journal notes, dashboard evidence, any routed
live rows for them, Setup 5's decision-log rows and its processed-signal ids. Everything is deleted in one transaction after a
consistent backup copy `<db>.before-setup5-purge-<timestamp>` is written next to the database. Not touched: other setups, the
append-only .jsonl log files, settings.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime

SETUP5 = "(setup_type LIKE 'Setup 5%' OR setup_type LIKE 'SETUP_5%')"
POS_IDS = f"SELECT id FROM positions WHERE {SETUP5}"


def _tables(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _plan(con: sqlite3.Connection) -> list[tuple[str, str]]:
    """(label, WHERE clause with its table) pairs: each is a `DELETE FROM <table> WHERE ...`."""
    t = _tables(con)
    plan = []
    if "positions" in t:
        plan.append(("positions", f"positions WHERE {SETUP5}"))
    for table, col in (("trade_candles", "position_id"), ("trade_excursions", "position_id"), ("trade_journal", "position_id"),
                       ("live_positions", "position_id"), ("live_orders", "position_id")):
        if table in t:
            plan.append((table, f"{table} WHERE {col} IN ({POS_IDS})"))
    if "dashboard_trade_evidence" in t:
        plan.append(("dashboard_trade_evidence", f"dashboard_trade_evidence WHERE book = 'paper' AND position_id IN ({POS_IDS})"))
    if "strategy_decisions" in t:
        plan.append(("strategy_decisions", "strategy_decisions WHERE strategy LIKE 'Setup 5%' OR strategy LIKE 'SETUP_5%'"))
    if "processed_signals" in t:
        plan.append(("processed_signals", "processed_signals WHERE signal_id LIKE '%\\_S5\\_%' ESCAPE '\\'"))
    return plan


def counts(con: sqlite3.Connection) -> dict[str, int]:
    return {label: con.execute(f"SELECT COUNT(*) FROM {where}").fetchone()[0] for label, where in _plan(con)}


def purge(db_path: str, execute: bool) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    try:
        found = counts(con)
        if not execute:
            return found
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = f"{db_path}.before-setup5-purge-{stamp}"
        dest = sqlite3.connect(backup_path)
        try:
            con.backup(dest)
        finally:
            dest.close()
        os.chmod(backup_path, 0o600)
        print(f"backup written: {backup_path}")
        with con:                       # one transaction: all or nothing
            # dependents first, then the positions they point at
            for label, where in reversed(_plan(con)):
                con.execute(f"DELETE FROM {where}")
        return found
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, help="path to trades.db")
    ap.add_argument("--yes", action="store_true", help="actually delete (a backup copy is written first)")
    args = ap.parse_args()
    if not os.path.exists(args.db):
        print(f"No database at {args.db}", file=sys.stderr)
        return 2
    found = purge(args.db, execute=args.yes)
    verb = "deleted" if args.yes else "would delete"
    for label, n in found.items():
        print(f"  {verb} {n:5d} rows from {label}")
    if not args.yes:
        print("dry run only: nothing changed. Stop the service, then rerun with --yes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
