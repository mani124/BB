#!/usr/bin/env python
"""Flag suspect historical paper-trade rows (off-session entries, stacked duplicates).

Dry run by default; pass --apply to write. Rows are never deleted, only flagged via
positions.quarantine_reason, and are then excluded from performance totals.

    python scripts/quarantine_bad_rows.py            # list what would be flagged
    python scripts/quarantine_bad_rows.py --apply    # flag them
    python scripts/quarantine_bad_rows.py --apply --ids POS_A POS_B --reason MANUAL_REVIEW
    python scripts/quarantine_bad_rows.py --clear --ids POS_A      # un-quarantine
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.services.paper_storage import PaperStorage  # noqa: E402
from app.services.quarantine import apply_quarantine, find_suspect_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=settings.DB_PATH)
    ap.add_argument("--apply", action="store_true", help="write flags (default is a dry run)")
    ap.add_argument("--ids", nargs="*", default=[], help="explicit position ids to flag/clear")
    ap.add_argument("--reason", default="MANUAL_QUARANTINE", help="reason used with --ids")
    ap.add_argument("--clear", action="store_true", help="clear the flag on --ids")
    args = ap.parse_args()

    # Instantiating PaperStorage also runs the schema migration/backfill (non-destructive).
    storage = PaperStorage(args.db)
    if args.clear:
        print(f"cleared {storage.clear_quarantine(args.ids)} row(s)")
        return 0

    suspects = find_suspect_rows(args.db)
    suspects.update({pid: args.reason for pid in args.ids})
    for pid, reason in sorted(suspects.items()):
        print(f"{reason:20s} {pid}")
    print(f"{len(suspects)} row(s) {'flagged' if args.apply else 'would be flagged (dry run)'}")
    if args.apply and suspects:
        apply_quarantine(args.db, suspects)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
