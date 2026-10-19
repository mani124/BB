"""Source-aware read models for the decision-focused dashboard."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services.paper_trader import paper_trader
from app.services.cx_registry import get_engine as get_cx_engine
from app.services.earnings_registry import get_engine as get_earnings_engine
from app.services.dashboard_evidence import evidence_ids
from app.services.market_hours import now_ist


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
        strike = _value(raw, "strike")
        strike_label = f"{strike:g}" if isinstance(strike, (int, float)) else str(strike or "")
        instrument = _value(raw, "option_symbol") or " ".join(part for part in (
            str(_value(raw, "symbol", "")), strike_label, str(_value(raw, "side", ""))) if part)
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
        "exit_reason": _value(raw, "exit_reason"),
        "signal_id": _value(raw, "signal_id"),
    }


def _all_trade_rows() -> list[dict]:
    portfolio = paper_trader.get_portfolio(None)
    rows = [_row("paper", p) for p in portfolio.active_positions + portfolio.closed_trades]
    rows += [_row("cx", p) for p in get_cx_engine().positions()]
    rows += [_row("earnings", p) for p in get_earnings_engine().positions()]
    by_book = {book: evidence_ids(book) for book in ("paper", "cx", "earnings")}
    for row in rows:
        if row["source_id"] in by_book[row["book"]]:
            row["evidence_state"] = "recorded"
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


def _ist_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata")).isoformat() if parsed.tzinfo is None else parsed.astimezone(ZoneInfo("Asia/Kolkata")).isoformat()
    except ValueError:
        return None


def get_dashboard_session(day: str) -> dict:
    """A selected IST day built only from stored decisions, errors and positions."""
    date.fromisoformat(day)
    telemetry = paper_trader.telemetry.day_events(day)
    all_trades = list_dashboard_trades()
    known_trade_ids = {row["id"] for row in all_trades}
    events: list[dict] = []
    for row in telemetry["decisions"]:
        at = _ist_iso(row.get("ts"))
        if not at:
            continue
        raw_book = row.get("book") or "paper"
        book = "paper" if raw_book in ("demo", "live") else raw_book
        position = row.get("position_id")
        trade_id = f"{book}:{position}" if position else None
        events.append({"id": f"decision:{row['id']}", "at": at, "type": "decision", "book": book,
                       "trade_id": trade_id if trade_id in known_trade_ids else None,
                       "instrument": row.get("symbol"), "title": f"{row.get('decision', 'Decision')} · {row.get('symbol', '')}",
                       "reason": row.get("reason"), "metrics": row.get("metrics") or {},
                       "evidence_id": f"decision:{row['id']}", "evidence_state": "recorded"})
    for row in telemetry["errors"]:
        at = _ist_iso(row.get("ts"))
        if not at:
            continue
        events.append({"id": f"error:{row['id']}", "at": at, "type": "error", "book": None,
                       "trade_id": None, "instrument": None, "title": row.get("code") or "Error",
                       "reason": row.get("message"), "metrics": row.get("payload") or {},
                       "evidence_id": f"error:{row['id']}", "evidence_state": "recorded"})

    for row in paper_trader.runtime.audit_day(day):
        at = _ist_iso(row.get("changed_at"))
        if not at:
            continue
        events.append({"id": f"setting:{row['id']}", "at": at, "type": "control", "book": None,
                       "trade_id": None, "instrument": None, "title": f"Setting changed · {row['key']}",
                       "reason": row["key"], "metrics": {"from": row.get("old_value"), "to": row.get("new_value"), "by": row.get("actor")},
                       "evidence_id": f"setting:{row['id']}", "evidence_state": "recorded"})

    by_book: list[dict] = []
    for book in ("paper", "cx", "earnings"):
        rows = [row for row in all_trades if row["book"] == book]
        touched = [row for row in rows if any((_ist_iso(row.get(key)) or "")[:10] == day for key in ("opened_at", "closed_at"))]
        realized = [row["net_pnl"] for row in touched if row.get("net_kind") == "realized" and row.get("closed_at") and (_ist_iso(row["closed_at"]) or "")[:10] == day and row.get("net_pnl") is not None]
        is_today = day == now_ist().date().isoformat()
        estimated = [row["net_pnl"] for row in rows if is_today and row.get("net_kind") == "estimated" and row.get("net_pnl") is not None]
        by_book.append({"book": book, "display_book": {"paper": "Main + Setup 16", "cx": "Commodities & FX", "earnings": "Earnings"}[book],
                        "entries": sum(1 for row in touched if (_ist_iso(row.get("opened_at")) or "")[:10] == day),
                        "exits": sum(1 for row in touched if (_ist_iso(row.get("closed_at")) or "")[:10] == day),
                        "open_positions": sum(1 for row in rows if row.get("status") in ("OPEN", "TARGET_1")) if is_today else None,
                        "realized_net": round(sum(realized), 2) if realized else None,
                        "estimated_net": round(sum(estimated), 2) if estimated else None})
        for row in touched:
            for kind, key in (("entry", "opened_at"), ("exit", "closed_at")):
                at = _ist_iso(row.get(key))
                if not at or at[:10] != day:
                    continue
                events.append({"id": f"{kind}:{row['id']}", "at": at, "type": kind, "book": book,
                               "trade_id": row["id"], "instrument": row.get("instrument"),
                               "title": f"{kind.title()} · {row.get('instrument', '')}",
                               "reason": row.get("exit_reason") if kind == "exit" else None,
                               "metrics": {}, "evidence_id": row["id"] if row.get("evidence_state") == "recorded" else None,
                               "evidence_state": row.get("evidence_state", "unavailable")})
    events.sort(key=lambda row: (row["at"], row["id"]))
    skipped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for event in events:
        if event["type"] == "decision" and event["title"].startswith("SKIPPED") and event["reason"]:
            skipped[(event["book"], event["reason"])].append(event["id"])
    observations = [{"id": f"skip:{book}:{reason}", "title": f"{len(ids)} skips: {reason}",
                     "detail": f"{book} recorded the same skip reason {len(ids)} times on this day.", "event_ids": ids}
                    for (book, reason), ids in skipped.items() if len(ids) >= 2]
    errors_by_code: dict[str, list[str]] = defaultdict(list)
    for event in events:
        if event["type"] == "error":
            errors_by_code[event["title"]].append(event["id"])
    observations.extend({"id": f"error:{code}", "title": f"{len(ids)} recorded errors: {code}",
                         "detail": "Review the linked error events and source health before relying on that feed.", "event_ids": ids}
                        for code, ids in errors_by_code.items() if len(ids) >= 2)
    return {"day": day, "timezone": "Asia/Kolkata", "events": events, "by_book": by_book, "observations": observations}


def _source(book: str, mode: str, as_of: str | None, observed_at: str, *, disabled: bool = False,
            error: str | None = None) -> dict:
    state = "unknown"
    if error or mode == "error":
        state = "error"
    elif disabled:
        state = "disabled"
    elif mode == "stale":
        state = "stale"
    elif as_of:
        try:
            age = datetime.fromisoformat(_ist_iso(observed_at)) - datetime.fromisoformat(_ist_iso(as_of))
            state = "stale" if age > timedelta(minutes=15) else "ready"
        except (TypeError, ValueError):
            state = "unknown"
    return {"book": book, "mode": mode, "as_of": as_of, "state": state, "message": error or ""}


def _checks(metrics: Any) -> list[dict]:
    return [{"name": str(k), "value": v} for k, v in metrics.items()] if isinstance(metrics, dict) else []


def build_dashboard_watch(snapshot: dict, setup16: dict, cx: dict, earnings: dict, *, observed_at: str) -> dict:
    """Combine source snapshots without treating on-demand previews as recorded decisions."""
    sources: list[dict] = []
    candidates: list[dict] = []

    signals = snapshot.get("signals") or []
    signal_times = [_timestamp(s.get("timestamp")) for s in signals]
    paper_as_of = _timestamp(snapshot.get("last_scan_at")) or max((t for t in signal_times if t), default=None)
    sources.append(_source("paper", str(snapshot.get("active_mode", "unknown")), paper_as_of, observed_at,
                           error=snapshot.get("_error")))
    for sig in signals:
        candidates.append({"id": f"paper:{sig.get('id')}", "book": "paper", "stage": "CONFIRMED" if sig.get("is_confirmed") else "WATCHING",
                           "observed_at": _timestamp(sig.get("timestamp")), "is_preview": False,
                           "checks": _checks(sig.get("indicators_snapshot")), "block_reason": None,
                           "instrument": sig.get("symbol", ""), "setup": sig.get("setup_type", ""),
                           "detail": sig.get("rationale", ""), "source_ref": sig})

    contracts = setup16.get("contracts") or []
    times: list[str] = []
    contract_times: dict[int, str] = {}
    for contract in contracts:
        try:
            timestamp = datetime.fromtimestamp(float(contract["updated_ts"]), ZoneInfo("Asia/Kolkata")).isoformat()
            times.append(timestamp)
            contract_times[id(contract)] = timestamp
        except (KeyError, TypeError, ValueError, OverflowError):
            pass
    s16_as_of = max(times, default=None)
    sources.append(_source("setup16", str(setup16.get("mode", "unknown")), s16_as_of, observed_at,
                           disabled=setup16.get("mode") == "off", error=setup16.get("_error")))
    for contract in contracts:
        symbol = str(contract.get("symbol") or contract.get("strike_symbol") or "unknown")
        side = str(contract.get("side") or contract.get("option_type") or "")
        candidates.append({"id": f"setup16:{symbol}:{side}", "book": "setup16", "stage": contract.get("stage", "NO_DATA"),
                           "observed_at": contract_times.get(id(contract)), "is_preview": False,
                           "checks": _checks({k: contract[k] for k in ("in_squeeze", "pct_to_upper") if k in contract}),
                           "block_reason": None, "instrument": symbol, "setup": "Setup 16", "detail": "",
                           "source_ref": contract})

    for name, payload in (("cx", cx), ("earnings", earnings)):
        summary = payload.get("summary") or {}
        cycle = summary.get("last_cycle") or {}
        as_of = _timestamp(cycle.get("at"))
        sources.append(_source(name, "paper", as_of, observed_at, disabled=summary.get("enabled") is False,
                               error=payload.get("_error") or (cycle.get("error") if cycle.get("status") == "error" else None)))
        for idx, candidate in enumerate(payload.get("candidates") or []):
            symbol = str(candidate.get("symbol", "unknown"))
            setup = str(candidate.get("setup") or candidate.get("mode") or "")
            code = str(candidate.get("code") or ("READY" if candidate.get("ready") else "WATCHING"))
            candidates.append({"id": f"{name}:{symbol}:{setup}:{idx}", "book": name, "stage": code,
                               "observed_at": observed_at, "is_preview": True,
                               "checks": _checks(candidate.get("metrics")),
                               "block_reason": candidate.get("detail") or (None if candidate.get("ready") else code),
                               "instrument": symbol, "setup": setup, "detail": candidate.get("detail", ""),
                               "source_ref": candidate})

    return {"observed_at": observed_at, "sources": sources, "candidates": candidates}
