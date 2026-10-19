"""Source-aware read models for the decision-focused dashboard."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.paper_trader import paper_trader
from app.services.cx_registry import get_engine as get_cx_engine
from app.services.earnings_registry import get_engine as get_earnings_engine


def _value(row: Any, key: str, default: Any = None) -> Any:
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def _timestamp(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return None
    return text


def _net(row: Any, status: str, closed_key: str, open_key: str) -> tuple[float | None, str]:
    is_open = status in ("OPEN", "TARGET_1")
    value = _value(row, open_key if is_open else closed_key)
    return (float(value) if value is not None else None, "estimated" if is_open else "realized")


def _row(book: str, raw: Any) -> dict:
    source_id = str(_value(raw, "id"))
    status = str(_value(raw, "status", "UNKNOWN"))
    if book == "paper":
        setup = str(_value(raw, "setup_type", ""))
        display_book = "Setup 16" if "Setup 16" in setup or "SETUP_16" in setup else "Main scanner"
        instrument = _value(raw, "strike_symbol") or _value(raw, "symbol", "")
        opened = _timestamp(_value(raw, "entry_datetime"))
        closed = _timestamp(_value(raw, "exit_datetime"))
        mode = _value(raw, "feed_mode", "demo")
        net, net_kind = _net(raw, status, "net_pnl", "est_net_pnl")
    elif book == "cx":
        setup = str(_value(raw, "setup", ""))
        display_book = "Commodities & FX"
        instrument = _value(raw, "option_symbol") or _value(raw, "symbol", "")
        opened = _timestamp(_value(raw, "opened_at"))
        closed = _timestamp(_value(raw, "closed_at"))
        mode = "paper"
        net, net_kind = _net(raw, status, "net_pnl", "unrealized_net")
    else:
        setup = str(_value(raw, "mode", ""))
        display_book = "Earnings"
        instrument = _value(raw, "symbol", "")
        opened = _timestamp(_value(raw, "opened_at"))
        closed = _timestamp(_value(raw, "closed_at"))
        mode = "paper"
        net, net_kind = _net(raw, status, "net_pnl", "unrealized_net")
    return {
        "id": f"{book}:{source_id}", "book": book, "display_book": display_book,
        "source_id": source_id, "status": status, "instrument": str(instrument),
        "setup": setup, "opened_at": opened, "closed_at": closed, "mode": mode,
        "net_pnl": net, "net_kind": net_kind, "evidence_state": "unavailable",
    }


def _all_trade_rows() -> list[dict]:
    portfolio = paper_trader.get_portfolio(None)
    rows = [_row("paper", p) for p in portfolio.active_positions + portfolio.closed_trades]
    rows += [_row("cx", p) for p in get_cx_engine().positions()]
    rows += [_row("earnings", p) for p in get_earnings_engine().positions()]
    return rows


def list_dashboard_trades(*, status: str | None = None, book: str | None = None, day: str | None = None) -> list[dict]:
    """All recorded positions, including old ones without complete evidence."""
    rows = _all_trade_rows()
    if status:
        rows = [r for r in rows if r["status"] == status]
    if book:
        rows = [r for r in rows if r["book"] == book or r["display_book"] == book]
    if day:
        rows = [r for r in rows if (r["opened_at"] or "")[:10] == day]
    return sorted(rows, key=lambda r: (r["opened_at"] or "", r["id"]), reverse=True)
