"""Journal views over closed paper trades: day filter, CSV export and a one-page daily summary.

Quarantined trades are excluded everywhere; archived (reset) trades are never loaded into the
engine, so they cannot appear. Win/loss uses the same net-of-charges basis as the dashboard.
"""
import csv
import html
import io
from datetime import date
from typing import Iterable, Optional

from app.services.paper_models import _parse_iso
from app.services.paper_trader import _outcome_pnl

CSV_COLUMNS = [
    "date", "symbol", "option", "strike", "setup", "timeframe", "feed", "lots", "quantity",
    "entry_time", "exit_time", "entry_price", "exit_reason", "gross_pnl", "charges", "net_pnl",
    "tag", "note",
]
# Spreadsheet apps run text starting with these as formulas; a note typed by hand must not.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def exit_date(p) -> Optional[str]:
    stamp = _parse_iso(p.exit_datetime) or _parse_iso(p.entry_datetime)
    return stamp.date().isoformat() if stamp else None


def select_trades(closed: Iterable, start: date, end: date, mode: Optional[str] = None) -> list:
    out = []
    for p in closed:
        if p.quarantine_reason:
            continue
        if mode is not None and getattr(p, "feed_mode", "demo") != mode:
            continue
        d = exit_date(p)
        if d is None or not (start.isoformat() <= d <= end.isoformat()):
            continue
        out.append(p)
    out.sort(key=lambda p: p.exit_datetime or p.entry_datetime or "")
    return out


def _safe(text: str) -> str:
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def _gross(p) -> float:
    return p.gross_pnl or p.pnl_rupees


def to_csv(trades: list, notes: dict[str, dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for p in trades:
        n = notes.get(p.id, {})
        w.writerow([
            exit_date(p), p.symbol, p.option_type, p.strike_symbol, p.setup_type, p.timeframe,
            p.feed_mode, p.lots, p.quantity, p.entry_time, p.exit_time or "", p.option_entry,
            _safe(p.exit_reason or ""), round(_gross(p), 2), round(p.total_charges, 2),
            round(p.net_pnl, 2), _safe(n.get("tag", "")), _safe(n.get("note", "")),
        ])
    return buf.getvalue()


def summarize(trades: list, notes: dict[str, dict]) -> dict:
    wins = [p for p in trades if _outcome_pnl(p) > 0]
    losses = [p for p in trades if _outcome_pnl(p) < 0]
    best = max(trades, key=_outcome_pnl, default=None)
    worst = min(trades, key=_outcome_pnl, default=None)

    def brief(p):
        return None if p is None else {
            "id": p.id, "symbol": p.symbol, "strike_symbol": p.strike_symbol, "net_pnl": round(p.net_pnl, 2),
        }

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(100.0 * len(wins) / len(trades), 1) if trades else 0.0,
        "gross_pnl": round(sum(_gross(p) for p in trades), 2),
        "total_charges": round(sum(p.total_charges for p in trades), 2),
        "net_pnl": round(sum(p.net_pnl for p in trades), 2),
        "best": brief(best),
        "worst": brief(worst),
        "notes": [
            {"id": p.id, "strike_symbol": p.strike_symbol, "net_pnl": round(p.net_pnl, 2),
             "tag": notes[p.id].get("tag", ""), "note": notes[p.id].get("note", "")}
            for p in trades if p.id in notes
        ],
    }


def _money(v: float) -> str:
    return f"{'-' if v < 0 else ''}₹{abs(v):,.2f}"


def render_summary_html(label: str, trades: list, notes: dict[str, dict], mode: Optional[str]) -> str:
    s = summarize(trades, notes)
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(p.exit_time or '')}</td><td>{e(p.strike_symbol)}</td><td>{e(p.setup_type)}</td>"
        f"<td class='n {'up' if p.net_pnl >= 0 else 'dn'}'>{e(_money(p.net_pnl))}</td>"
        f"<td>{e(notes.get(p.id, {}).get('tag', ''))}</td></tr>"
        for p in trades
    ) or "<tr><td colspan='5'>No closed trades.</td></tr>"
    note_items = "".join(
        f"<li><b>{e(n['strike_symbol'])}</b> ({e(_money(n['net_pnl']))})"
        f"{' [' + e(n['tag']) + ']' if n['tag'] else ''}: {e(n['note'])}</li>"
        for n in s["notes"] if n["note"]
    ) or "<li>No notes.</li>"

    def ext(t):
        return "-" if t is None else f"{e(t['strike_symbol'])} {e(_money(t['net_pnl']))}"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Daily summary {e(label)}</title>
<style>
@page {{ size: A4; margin: 14mm; }}
body {{ font: 13px/1.4 system-ui, sans-serif; color: #111; max-width: 780px; margin: 24px auto; padding: 0 16px; }}
h1 {{ font-size: 20px; margin: 0 0 2px; }} .sub {{ color: #555; margin-bottom: 14px; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 14px; }}
.kpi {{ border: 1px solid #ccc; border-radius: 6px; padding: 8px; }}
.kpi span {{ display: block; color: #555; font-size: 11px; }} .kpi b {{ font-size: 16px; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 14px; }}
th, td {{ text-align: left; padding: 4px 6px; border-bottom: 1px solid #ddd; }}
.n {{ text-align: right; }} .up {{ color: #0a7a3c; }} .dn {{ color: #b3261e; }}
h2 {{ font-size: 14px; margin: 14px 0 6px; }}
</style></head><body>
<h1>Daily trading summary</h1>
<div class="sub">{e(label)} · {e(mode or 'all feeds')} · closed trades only, quarantined excluded</div>
<div class="kpis">
<div class="kpi"><span>Trades</span><b>{s['trades']}</b></div>
<div class="kpi"><span>Win rate</span><b>{s['win_rate']}% ({s['wins']}W / {s['losses']}L)</b></div>
<div class="kpi"><span>Net P&amp;L</span><b class="{'up' if s['net_pnl'] >= 0 else 'dn'}">{e(_money(s['net_pnl']))}</b></div>
<div class="kpi"><span>Charges</span><b>{e(_money(s['total_charges']))}</b></div>
</div>
<div>Best: <b>{ext(s['best'])}</b> · Worst: <b>{ext(s['worst'])}</b></div>
<h2>Trades</h2>
<table><tr><th>Exit</th><th>Contract</th><th>Setup</th><th class="n">Net</th><th>Tag</th></tr>{rows}</table>
<h2>Notes</h2><ul>{note_items}</ul>
</body></html>"""
