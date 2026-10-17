"""Live order routing: the single gate between the paper engine and a real broker.

How it fits. The paper engine stays the strategy brain and the source of truth for signals, sizing and exits.
When routing is on, each *real-feed* paper entry is mirrored to the broker as a BUY, and each paper exit (stop,
Target 1 half, Target 2, manual, kill switch, end of day) as a SELL of whatever the broker still holds for that
position. With routing off the engine behaves exactly as before: every hook below returns immediately.

Modes (``mode``): ``off`` (default), ``dry_run`` (build and log the exact order, run every check, send nothing)
and ``live``. Live is never a setting. It needs the env confirm flag, a one-time code from ``arm()``, a typed
phrase, a verified broker session and no halt; it drops back to ``dry_run`` on every restart.

Order of authority for an *entry*: mode -> halt -> kill switch / loss cap / loss streak -> entry window ->
setup allow-list -> inputs present -> live loss limit -> size, value and count caps -> contract resolution ->
duplicate tag. Every check fails closed: a missing number blocks the order. An *exit* is never blocked by any of
these (only by having nothing left to sell), and it goes to the broker for real whenever the position was
bought for real, whatever the mode is by then.

Idempotency: a tag is reserved in ``order_tags`` (survives restarts) before any send. It is released only on a
definite "not accepted"; on a timeout it stays, the order is looked up at the broker by tag, and if that fails
the router halts entries and raises a CRITICAL alert instead of sending again.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import threading
import time
from typing import Any, Callable, Optional

from app.services import market_hours
from app.services.broker_adapter import (
    ACTIVE_STATES, CANCELED, COMPLETE, FINAL_STATES, NEW, OPEN, REJECTED, UNKNOWN, BrokerAdapter,
    BrokerAuthExpired, BrokerError, BrokerNotSent, BrokerRejected, BrokerTimeout, Contract, OrderRequest,
    OrderResult,
)
from app.services.notifier import notify
from app.services import db

logger = logging.getLogger(__name__)

OFF, DRY_RUN, LIVE = "off", "dry_run", "live"
MODES = (OFF, DRY_RUN, LIVE)
ENABLE_PHRASE = "ENABLE LIVE TRADING"
CONFIRM_ENV = "LIVE_TRADING_CONFIRM"
ARM_TTL_SECONDS = 120
CLOSED_STATUSES = ("STOPPED_OUT", "TARGET_2", "CLOSED")
MAX_AUTO_EXIT_FAILURES = 3
_OPEN_ORDER_STATES = ("SENDING", NEW, OPEN, UNKNOWN)


def _today() -> str:
    return market_hours.now_ist().date().isoformat()


def _now() -> str:
    return market_hours.now_ist().strftime("%Y-%m-%d %H:%M:%S")


def round_tick(price: float, tick: float = 0.05, up: bool = True) -> float:
    n = price / tick
    n = math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)
    return round(max(tick, n * tick), 2)


def setup_number(setup_type: str) -> Optional[int]:
    m = re.search(r"Setup\s+(\d+)", str(setup_type or ""))
    return int(m.group(1)) if m else None


def parse_allowed_setups(text: str) -> set[int]:
    return {int(t) for t in re.findall(r"\d+", str(text or ""))}


class OrderRouter:
    def __init__(self, db_path: str, runtime: Any, telemetry: Any, engine: Any, broker: BrokerAdapter, *,
                 notify_fn: Callable[..., Any] = notify, sleep: Callable[[float], Any] = asyncio.sleep) -> None:
        self.db_path = db_path
        self.runtime = runtime
        self.telemetry = telemetry
        self.engine = engine
        self.broker = broker
        self._notify = notify_fn
        self._sleep = sleep
        self._dblock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._entry_lock: Optional[asyncio.Lock] = None
        self._pos_locks: dict[str, asyncio.Lock] = {}
        self._tracked: set[str] = set()
        self._last_key: dict[str, tuple] = {}
        self._exit_failures: dict[str, int] = {}
        self._arm: Optional[dict] = None
        self._mode = OFF
        self._init_db()
        self._restore()

    # ------------------------------------------------------------------ storage
    def _conn(self) -> sqlite3.Connection:
        conn = db.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._dblock, self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS live_positions (
                position_id TEXT PRIMARY KEY, symbol TEXT, strike_symbol TEXT, setup TEXT, exchange TEXT,
                trading_symbol TEXT, lot_size INTEGER, req_qty INTEGER, paper_qty INTEGER, mode TEXT, state TEXT,
                opened_at TEXT, closed_at TEXT, last_error TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS live_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT, position_id TEXT, side TEXT, tag TEXT,
                mode TEXT, exchange TEXT, trading_symbol TEXT, qty INTEGER, order_type TEXT, price REAL,
                broker_order_id TEXT, status TEXT, filled_qty INTEGER DEFAULT 0, avg_price REAL DEFAULT 0,
                message TEXT, payload TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_live_orders_pos ON live_orders(position_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_live_orders_day ON live_orders(day, mode)")
            c.execute("""CREATE TABLE IF NOT EXISTS order_tags (
                tag TEXT PRIMARY KEY, position_id TEXT, reserved_at TEXT, state TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS live_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, detail TEXT)""")
            c.execute("CREATE TABLE IF NOT EXISTS live_state (key TEXT PRIMARY KEY, value TEXT)")

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._dblock, self._conn() as c:
            return c.execute(sql, args).fetchall()

    def _x(self, sql: str, args: tuple = ()) -> int:
        with self._dblock, self._conn() as c:
            cur = c.execute(sql, args)
            return cur.lastrowid or 0

    def _get_state(self, key: str, default: str = "") -> str:
        rows = self._q("SELECT value FROM live_state WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def _set_state(self, key: str, value: str) -> None:
        self._x("INSERT OR REPLACE INTO live_state (key, value) VALUES (?, ?)", (key, value))

    def audit(self, action: str, detail: str = "", actor: str = "dashboard") -> None:
        self._x("INSERT INTO live_audit (ts, actor, action, detail) VALUES (?,?,?,?)", (_now(), actor, action, detail[:500]))

    def _restore(self) -> None:
        saved = self._get_state("mode", OFF)
        self._mode = saved if saved in MODES else OFF
        if self._mode == LIVE:
            self._mode = DRY_RUN
            self._set_state("mode", DRY_RUN)
            self.audit("mode", "live -> dry_run: live never survives a restart; arm again to go live", actor="system")
        for r in self._q("SELECT position_id FROM live_positions WHERE state IN ('ENTERING','OPEN')"):
            self._tracked.add(r["position_id"])

    # ------------------------------------------------------------------ plumbing
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _get_entry_lock(self) -> asyncio.Lock:
        if self._entry_lock is None:
            self._entry_lock = asyncio.Lock()
        return self._entry_lock

    def _pos_lock(self, pid: str) -> asyncio.Lock:
        lk = self._pos_locks.get(pid)
        if lk is None:
            lk = self._pos_locks[pid] = asyncio.Lock()
        return lk

    def _submit(self, coro) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            coro.close()
            self._err("LIVE_NO_LOOP", "Router has no running event loop; the order was not handled.", "CRITICAL")
            return
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        fut.add_done_callback(self._log_future)

    def _log_future(self, fut) -> None:
        try:
            exc = fut.exception()
        except Exception:
            return
        if exc is not None:
            self._err("LIVE_TASK_FAILED", f"{type(exc).__name__}: {exc}", "CRITICAL")

    def _err(self, code: str, message: str, severity: str = "ERROR", payload: Optional[dict] = None) -> None:
        log = logger.error if severity in ("ERROR", "CRITICAL") else logger.warning
        log("%s %s", code, message)
        try:
            self.telemetry.error(code=code, component="order_router", message=message, severity=severity,
                                 payload=payload or {})
        except Exception:
            pass

    def _alert(self, event: str, text: str, key: Optional[str] = None, min_interval: float = 60) -> None:
        try:
            self._notify(event, text, dedupe_key=key or event, min_interval=min_interval)
        except Exception:
            logger.warning("live alert failed: %s", event, exc_info=True)

    # ------------------------------------------------------------------ mode / arming / halt
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def halted(self) -> str:
        return self._get_state("halted", "")

    @staticmethod
    def env_confirmed() -> bool:
        return os.getenv(CONFIRM_ENV, "") == "CONFIRMED"

    def set_mode(self, mode: str, actor: str = "dashboard") -> str:
        """off and dry_run can be chosen freely. live only through enable_live()."""
        if mode == LIVE:
            raise PermissionError("Live is enabled only through arm() then enable_live().")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        old, self._mode = self._mode, mode
        self._set_state("mode", mode)
        self._arm = None
        if old != mode:
            self.audit("mode", f"{old} -> {mode}", actor)
            if old == LIVE:
                self._alert("live_off", f"Live routing switched to {mode}. Open routed positions still exit for real.",
                            min_interval=0)
        return self._mode

    def arm(self, actor: str = "dashboard") -> dict:
        """Step 1 of going live: returns a one-time code, valid ARM_TTL_SECONDS, after the pre-checks."""
        problems = self.live_preconditions(check_session=False)
        if problems:
            raise PermissionError("; ".join(problems))
        code = f"{secrets.randbelow(10**6):06d}"
        self._arm = {"code": code, "expires": time.monotonic() + ARM_TTL_SECONDS, "tries": 0}
        self.audit("arm", "one-time code issued", actor)
        return {"code": code, "expires_in": ARM_TTL_SECONDS, "phrase": ENABLE_PHRASE}

    def live_preconditions(self, check_session: bool = True) -> list[str]:
        out = []
        if not self.env_confirmed():
            out.append(f"server env {CONFIRM_ENV}=CONFIRMED is not set")
        if self.halted:
            out.append(f"entries are halted ({self.halted}); resume first")
        if getattr(self.engine, "_kill_switch", False):
            out.append("kill switch is engaged")
        if not str(self.runtime.get("live_algo_id")).strip():
            out.append("live_algo_id is empty")
        if not parse_allowed_setups(self.runtime.get("live_allowed_setups")):
            out.append("live_allowed_setups is empty")
        if float(self.runtime.get("live_daily_loss_limit")) <= 0 and float(self.runtime.get("daily_loss_limit")) <= 0:
            out.append("no daily loss limit is set")
        if check_session and not self.broker.has_session():
            out.append("no broker session; log in first")
        return out

    async def enable_live(self, code: str, phrase: str, actor: str = "dashboard") -> str:
        """Step 2: the code from arm(), the typed phrase, and a session that the broker accepts right now."""
        a = self._arm
        if not a or time.monotonic() > a["expires"]:
            self._arm = None
            raise PermissionError("Arm first: the code is missing or has expired.")
        if a["tries"] >= 3:
            self._arm = None
            raise PermissionError("Too many wrong attempts. Arm again.")
        if not secrets.compare_digest(str(code).strip(), a["code"]) or phrase.strip() != ENABLE_PHRASE:
            a["tries"] += 1
            raise PermissionError("The code or the typed phrase does not match.")
        problems = self.live_preconditions(check_session=True)
        if problems:
            raise PermissionError("; ".join(problems))
        try:
            await self.broker.verify_session()
        except BrokerError as exc:
            raise PermissionError(f"Broker session is not usable: {exc}") from None
        self._arm = None
        self._mode = LIVE
        self._set_state("mode", LIVE)
        self.audit("mode", "-> live", actor)
        self._alert("live_on", "LIVE order routing ENABLED. Entries for the allowed setups now go to the broker.",
                    min_interval=0)
        return self._mode

    def _halt(self, code: str, detail: str = "") -> None:
        if self.halted:
            return
        self._set_state("halted", code)
        self.audit("halt", f"{code}: {detail}", actor="system")
        self._err("LIVE_HALT", f"Entries halted: {code}. {detail}", "CRITICAL")
        self._alert("live_halt", f"LIVE routing HALTED ({code}): new entries stopped. {detail} Check the broker.",
                    key=f"halt:{code}", min_interval=300)

    async def resume(self, actor: str = "dashboard") -> dict:
        """Clear a halt, but only if a fresh reconcile finds nothing wrong."""
        if not self.halted:
            return {"halted": "", "mismatches": []}
        self._set_state("halted", "")
        result = await self.reconcile()
        if result["mismatches"] or result["unknown_orders"]:
            self._halt("RESUME_FAILED", "reconcile still shows differences")
        else:
            self.audit("resume", "halt cleared after clean reconcile", actor)
        return {"halted": self.halted, **result}

    # ------------------------------------------------------------------ small queries
    def _row(self, pid: str) -> Optional[sqlite3.Row]:
        r = self._q("SELECT * FROM live_positions WHERE position_id = ?", (pid,))
        return r[0] if r else None

    def _label(self) -> str:
        return "LIVE" if self._mode == LIVE else "DRY"

    def _held(self, pid: str) -> tuple[int, int]:
        """(held, pending_sell) from the order rows. Dry-run rows count as filled so the virtual book works."""
        held = pending = 0
        for r in self._q("SELECT side, qty, filled_qty, status FROM live_orders WHERE position_id = ? AND status != 'BLOCKED'", (pid,)):
            if r["side"] == "BUY":
                held += r["filled_qty"]
            else:
                held -= r["filled_qty"]
                if r["status"] in _OPEN_ORDER_STATES:
                    pending += max(0, r["qty"] - r["filled_qty"])
        return held, pending

    def _bought(self, pid: str) -> int:
        r = self._q("SELECT COALESCE(SUM(filled_qty),0) AS q FROM live_orders WHERE position_id=? AND side='BUY'", (pid,))
        return int(r[0]["q"])

    def _count(self, where: str, args: tuple = ()) -> int:
        return int(self._q(f"SELECT COUNT(*) AS n FROM live_orders WHERE day = ? AND mode = ? AND {where}",
                           (_today(), self._label()) + args)[0]["n"])

    def realized_today(self) -> float:
        """Rupee result of routed positions fully closed today (broker fills, before charges)."""
        total = 0.0
        for p in self._q("SELECT position_id FROM live_positions WHERE state='CLOSED' AND mode=? AND substr(closed_at,1,10)=?",
                         (self._label(), _today())):
            for o in self._q("SELECT side, filled_qty, avg_price FROM live_orders WHERE position_id=?", (p["position_id"],)):
                total += (1 if o["side"] == "SELL" else -1) * o["filled_qty"] * o["avg_price"]
        return round(total, 2)

    def _engine_position(self, pid: str):
        """(position, closed). A position the engine no longer has counts as closed: exits always go."""
        pf = self.engine._portfolio
        for p in pf.active_positions:
            if p.id == pid:
                return p, p.status in CLOSED_STATUSES
        for p in reversed(pf.closed_trades):
            if p.id == pid:
                return p, True
        return None, True

    # ------------------------------------------------------------------ engine hooks (sync, cheap)
    def on_entry(self, pos: Any, rec: Any) -> None:
        if self._mode == OFF or getattr(pos, "feed_mode", "demo") != "live":
            return
        try:
            ctx = {
                "id": pos.id, "symbol": pos.symbol, "option_type": pos.option_type, "setup": pos.setup_type,
                "strike_symbol": pos.strike_symbol, "lots": pos.lots, "qty": pos.quantity, "lot_size": pos.lot_size,
                "entry": pos.option_entry, "ask": getattr(rec, "real_ask_price", None) or pos.option_entry,
                "strike": getattr(rec, "recommended_strike", None), "expiry": getattr(rec, "expiry_date", None),
                "segment": _exchange_segment(pos.symbol),
            }
        except Exception:
            self._err("LIVE_ENTRY_CONTEXT", "Could not read the new position for routing.", "ERROR")
            return
        self._submit(self.enter(ctx))

    def on_position_update(self, pos: Any) -> None:
        if pos.id not in self._tracked:
            return
        key = (pos.status in CLOSED_STATUSES, pos.quantity)
        if self._last_key.get(pos.id) == key:
            return
        self._last_key[pos.id] = key
        self._submit(self.sync_position(pos.id))

    # ------------------------------------------------------------------ entry
    def _base_tag(self, pid: str) -> str:
        return "BB" + hashlib.sha1(pid.encode()).hexdigest()[:10]

    def _reserve_tag(self, tag: str, pid: str) -> bool:
        try:
            self._x("INSERT INTO order_tags (tag, position_id, reserved_at, state) VALUES (?,?,?,'RESERVED')", (tag, pid, _now()))
            return True
        except sqlite3.IntegrityError:
            return False

    def _tag_state(self, tag: str, state: str) -> None:
        if state == "RELEASED":
            self._x("DELETE FROM order_tags WHERE tag = ?", (tag,))
        else:
            self._x("UPDATE order_tags SET state = ? WHERE tag = ?", (state, tag))

    def _record_block(self, ctx: dict, code: str, reason: str) -> None:
        logger.info("Live entry blocked for %s: %s (%s)", ctx["symbol"], code, reason)
        self._x("INSERT INTO live_orders (ts, day, position_id, side, tag, mode, qty, status, message) VALUES (?,?,?,?,?,?,?,?,?)",
                (_now(), _today(), ctx["id"], "BUY", "", self._label(), ctx.get("qty", 0), "BLOCKED", f"{code}: {reason}"[:300]))
        try:
            self.telemetry.decision(book="live", strategy=ctx["setup"], symbol=ctx["symbol"], side=ctx["option_type"],
                                    decision="SKIPPED", reason=f"LIVE_{code}", position_id=ctx["id"],
                                    metrics={"reason": reason, "router_mode": self._mode})
        except Exception:
            pass

    def _entry_price(self, ctx: dict) -> float:
        if self.runtime.get("live_entry_order_type") == "MARKET":
            return 0.0
        return round_tick(float(ctx["ask"]) * (1 + float(self.runtime.get("live_entry_limit_buffer_pct")) / 100.0))

    def _gate(self, ctx: dict) -> Optional[tuple[str, str]]:
        """First failing check as (code, reason), or None. Pure reads, in the documented order."""
        if self.halted:
            return "HALTED", f"entries halted: {self.halted}"
        if getattr(self.engine, "_kill_switch", False):
            return "KILL_SWITCH", "kill switch is engaged"
        pool = "s11" if "Setup 11" in str(ctx["setup"]) else "main"
        reason = self.engine.risk_block_reason("live", pool)
        if reason:
            return "RISK_BLOCK", reason
        if not market_hours.is_entry_allowed():
            return "OUTSIDE_ENTRY_WINDOW", "outside the entry window"
        n = setup_number(ctx["setup"])
        if n is None or n not in parse_allowed_setups(self.runtime.get("live_allowed_setups")):
            return "SETUP_NOT_ALLOWED", f"{ctx['setup']} is not in live_allowed_setups"
        if self._mode == LIVE and not self.broker.has_session():
            return "NO_BROKER_SESSION", "no broker session"
        if not str(self.runtime.get("live_algo_id")).strip():
            return "NO_ALGO_ID", "live_algo_id is empty"
        try:
            lots, qty, lot_size = int(ctx["lots"]), int(ctx["qty"]), int(ctx["lot_size"])
            ask = float(ctx["ask"])
            strike = float(ctx["strike"])
        except (TypeError, ValueError):
            return "MISSING_INPUT", "lots, quantity, lot size, price or strike is missing"
        if min(lots, qty, lot_size) <= 0 or ask <= 0 or strike <= 0 or not ctx.get("expiry") or qty != lots * lot_size:
            return "MISSING_INPUT", "lots, quantity, lot size, price, strike or expiry is missing or inconsistent"
        limit = float(self.runtime.get("live_daily_loss_limit")) or float(self.runtime.get("daily_loss_limit"))
        if limit <= 0:
            return "LOSS_LIMIT_UNSET", "no live or general daily loss limit is set"
        worst = min(float(self.engine.day_pnl("live", None)), self.realized_today())
        if worst <= -limit:
            return "LOSS_CAP", f"day P&L {worst:,.0f} reached -{limit:,.0f}"
        if lots > int(self.runtime.get("live_max_lots_per_order")):
            return "LOTS_EXCEED", f"{lots} lots > cap {int(self.runtime.get('live_max_lots_per_order'))}"
        price = self._entry_price(ctx) or ask
        if qty * price > float(self.runtime.get("live_max_order_value")):
            return "VALUE_EXCEED", f"order value {qty * price:,.0f} > cap {float(self.runtime.get('live_max_order_value')):,.0f}"
        if self._count("side = 'BUY' AND status != 'BLOCKED'") >= int(self.runtime.get("live_max_entries_per_day")):
            return "ENTRY_CAP", "daily entry order cap reached"
        if self._count("status != 'BLOCKED'") >= int(self.runtime.get("live_max_orders_per_day")):
            return "ORDER_CAP", "daily order cap reached"
        open_n = int(self._q("SELECT COUNT(*) AS n FROM live_positions WHERE mode=? AND state IN ('ENTERING','OPEN')",
                             (self._label(),))[0]["n"])
        if open_n >= int(self.runtime.get("live_max_open_positions")):
            return "OPEN_CAP", f"{open_n} routed positions already open"
        return None

    async def enter(self, ctx: dict) -> Optional[str]:
        """Gate, resolve, reserve, then send (live) or log (dry run). Returns the order status or None if blocked."""
        if self._mode == OFF:
            return None
        pid = ctx["id"]
        async with self._get_entry_lock():
            blocked = self._gate(ctx)
            if blocked:
                self._record_block(ctx, *blocked)
                return None
            try:
                contract = await self.broker.resolve_contract(
                    underlying=ctx["symbol"], expiry=str(ctx["expiry"]), strike=float(ctx["strike"]),
                    option_type=ctx["option_type"], segment=_broker_segment(ctx["segment"]))
            except BrokerError as exc:
                self._record_block(ctx, "CONTRACT_UNRESOLVED", str(exc))
                self._err("LIVE_CONTRACT_UNRESOLVED", f"{ctx['symbol']}: {exc}", "WARNING")
                return None
            if contract.lot_size != int(ctx["lot_size"]):
                self._record_block(ctx, "LOT_MISMATCH", f"broker lot {contract.lot_size} vs ours {ctx['lot_size']}")
                return None
            tag = self._base_tag(pid) + "B"
            if not self._reserve_tag(tag, pid):
                self._record_block(ctx, "DUPLICATE_BLOCKED", f"tag {tag} already used")
                return None
            order_type = self.runtime.get("live_entry_order_type")
            req = OrderRequest(tag=tag, contract=contract, side="BUY", quantity=int(ctx["qty"]), order_type=order_type,
                               price=self._entry_price(ctx), product=self.runtime.get("live_product_type"),
                               algo_id=str(self.runtime.get("live_algo_id")).strip())
            self._x("""INSERT OR REPLACE INTO live_positions (position_id, symbol, strike_symbol, setup, exchange,
                       trading_symbol, lot_size, req_qty, paper_qty, mode, state, opened_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, ctx["symbol"], ctx["strike_symbol"], ctx["setup"], contract.exchange, contract.trading_symbol,
                     contract.lot_size, req.quantity, req.quantity, self._label(), "ENTERING", _now()))
            self._tracked.add(pid)
        async with self._pos_lock(pid):
            if self._mode != LIVE:
                self._log_dry(pid, req, "dry-run: nothing was sent")
                self._set_pos_state(pid, "OPEN")
                result = "DRY_RUN"
            else:
                result = await self._send_and_confirm(pid, req, entry=True)
        # The paper position may have changed size or closed while the entry was filling.
        if self._engine_position(pid)[0] is not None:
            await self.sync_position(pid)
        return result

    def _payload(self, req: OrderRequest) -> dict:
        return {"exchange": req.contract.exchange, "tradingsymbol": req.contract.trading_symbol, "side": req.side,
                "quantity": req.quantity, "price_type": req.order_type, "price": req.price, "product": req.product,
                "validity": req.validity, "algo_id": req.algo_id, "remarks": req.tag}

    def _log_dry(self, pid: str, req: OrderRequest, message: str) -> int:
        oid = self._x(
            """INSERT INTO live_orders (ts, day, position_id, side, tag, mode, exchange, trading_symbol, qty, order_type,
               price, status, filled_qty, avg_price, message, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_now(), _today(), pid, req.side, req.tag, "DRY", req.contract.exchange, req.contract.trading_symbol,
             req.quantity, req.order_type, req.price, "DRY_RUN", req.quantity, req.price, message,
             json.dumps(self._payload(req))))
        logger.info("DRY RUN %s", json.dumps(self._payload(req)))
        self._tag_state(req.tag, "DONE")
        return oid

    def _set_pos_state(self, pid: str, state: str, err: str = "") -> None:
        closed = _now() if state in ("CLOSED", "FAILED") else None
        self._x("UPDATE live_positions SET state = ?, closed_at = COALESCE(?, closed_at), last_error = ? WHERE position_id = ?",
                (state, closed, err[:300], pid))
        if state in ("ENTERING", "OPEN"):
            self._tracked.add(pid)
        else:
            self._tracked.discard(pid)
            self._last_key.pop(pid, None)

    # ------------------------------------------------------------------ send / confirm
    def _update_order(self, oid: int, res: OrderResult, status: Optional[str] = None) -> None:
        self._x("UPDATE live_orders SET broker_order_id = COALESCE(NULLIF(?, ''), broker_order_id), status = ?, "
                "filled_qty = ?, avg_price = ?, message = ? WHERE id = ?",
                (res.broker_order_id, status or res.status, res.filled_qty, res.avg_price, (res.message or "")[:300], oid))

    async def _send_and_confirm(self, pid: str, req: OrderRequest, entry: bool) -> str:
        oid = self._x(
            """INSERT INTO live_orders (ts, day, position_id, side, tag, mode, exchange, trading_symbol, qty, order_type,
               price, status, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_now(), _today(), pid, req.side, req.tag, "LIVE", req.contract.exchange, req.contract.trading_symbol,
             req.quantity, req.order_type, req.price, "SENDING", json.dumps(self._payload(req))))
        label = f"{req.side} {req.quantity} {req.contract.trading_symbol}"
        try:
            res = await self.broker.place_order(req)
        except (BrokerNotSent, BrokerRejected) as exc:
            self._tag_state(req.tag, "RELEASED")
            self._update_order(oid, OrderResult(status=REJECTED, message=str(exc)))
            await self._after_fail(pid, req, entry, f"{label} not accepted: {exc}")
            return REJECTED
        except BrokerAuthExpired as exc:
            self._tag_state(req.tag, "RELEASED")
            self._update_order(oid, OrderResult(status=REJECTED, message="BROKER_SESSION_EXPIRED"))
            self._halt("BROKER_SESSION_EXPIRED", "Log in to the broker again.")
            await self._after_fail(pid, req, entry, f"{label} not sent: broker session expired")
            return REJECTED
        except BrokerTimeout as exc:
            self._tag_state(req.tag, "UNKNOWN")
            self._update_order(oid, OrderResult(status=UNKNOWN, message=f"no answer: {exc}"))
            self._err("LIVE_ORDER_UNKNOWN", f"{label}: no answer from the broker ({exc}); looking it up by tag.", "CRITICAL")
            res = await self._lookup_by_tag(req.tag)
            if res is None:
                self._halt("ORDER_UNKNOWN", f"{label} may be live at the broker; check the order book.")
                if entry:
                    self._set_pos_state(pid, "OPEN")  # unknown fill: stay tracked, reconcile settles it
                return UNKNOWN
        self._tag_state(req.tag, "SENT")
        self._update_order(oid, res)
        final = await self._await_fill(oid, req, res)
        self._refresh_position(pid, entry)
        return final.status

    async def _lookup_by_tag(self, tag: str, attempts: int = 3) -> Optional[OrderResult]:
        for _ in range(attempts):
            try:
                res = await self.broker.find_order_by_tag(tag)
                if res is not None:
                    return res
            except BrokerError:
                pass
            await self._sleep(1.0)
        return None

    async def _await_fill(self, oid: int, req: OrderRequest, res: OrderResult) -> OrderResult:
        polls = max(1, int(self.runtime.get("live_order_timeout_seconds")))
        for _ in range(polls):
            if res.status in FINAL_STATES:
                return res
            await self._sleep(1.0)
            try:
                res = await self.broker.get_order(res.broker_order_id)
            except BrokerAuthExpired:
                self._halt("BROKER_SESSION_EXPIRED", "Log in to the broker again.")
                break
            except BrokerError:
                continue
            self._update_order(oid, res)
        if res.status not in FINAL_STATES and (req.side == "BUY" or req.order_type == "LIMIT"):
            try:  # an entry never waits forever, and a stale limit exit is cancelled so it can be re-sent
                await self.broker.cancel_order(res.broker_order_id)
                await self._sleep(1.0)
                res = await self.broker.get_order(res.broker_order_id)
                self._update_order(oid, res)
            except BrokerError as exc:
                self._err("LIVE_CANCEL_FAILED", f"{req.side} {req.contract.trading_symbol}: {exc}", "ERROR")
        return res

    async def _after_fail(self, pid: str, req: OrderRequest, entry: bool, text: str) -> None:
        if entry:
            self._set_pos_state(pid, "FAILED", text)
            self._alert("live_entry_failed", f"Live ENTRY failed: {text}", key=f"ef:{req.tag}", min_interval=0)
        else:
            self._exit_failures[pid] = self._exit_failures.get(pid, 0) + 1
            self._err("LIVE_EXIT_FAILED", text, "CRITICAL")
            self._alert("live_exit_failed", f"Live EXIT failed, position still open at the broker: {text}",
                        key=f"xf:{req.tag}", min_interval=0)

    def _refresh_position(self, pid: str, entry: bool = False) -> None:
        """Derive the position state from its order rows. `entry` only turns on the entry alerts."""
        row = self._row(pid)
        if not row or row["state"] in ("CLOSED", "FAILED"):
            return
        held, pending = self._held(pid)
        bought = self._bought(pid)
        if bought == 0:
            open_buy = self._q("SELECT 1 FROM live_orders WHERE position_id=? AND side='BUY' AND status IN ('SENDING','NEW','OPEN','UNKNOWN')", (pid,))
            if not open_buy:
                self._set_pos_state(pid, "FAILED", "entry did not fill")
                self._alert("live_entry_unfilled", f"Live entry not filled and cancelled: {row['strike_symbol']}.",
                            key=f"eu:{pid}", min_interval=0)
            return
        if held <= 0 and pending == 0:
            self._set_pos_state(pid, "CLOSED")
            self._exit_failures.pop(pid, None)
            self._alert("live_exit", f"Live position closed: {row['strike_symbol']}, sold @ {self._avg(pid, 'SELL'):.2f}.",
                        key=f"cl:{pid}", min_interval=0)
            return
        if row["state"] == "ENTERING":
            self._set_pos_state(pid, "OPEN")
        if entry:
            if bought < row["req_qty"]:
                self._alert("live_entry_partial", f"Live entry partly filled: {bought} of {row['req_qty']} on {row['strike_symbol']}.",
                            key=f"ep:{pid}", min_interval=0)
            self._alert("live_entry", f"Live ENTRY {row['strike_symbol']}: bought {bought} @ {self._avg(pid, 'BUY'):.2f}",
                        key=f"en:{pid}", min_interval=0)

    def _avg(self, pid: str, side: str) -> float:
        rows = self._q("SELECT filled_qty, avg_price FROM live_orders WHERE position_id=? AND side=? AND filled_qty>0", (pid, side))
        q = sum(r["filled_qty"] for r in rows)
        return sum(r["filled_qty"] * r["avg_price"] for r in rows) / q if q else 0.0

    # ------------------------------------------------------------------ exits
    async def sync_position(self, pid: str) -> Optional[str]:
        """Bring the broker's holding for one position in line with the paper position. Never gated by risk checks."""
        async with self._pos_lock(pid):
            row = self._row(pid)
            if not row or row["state"] != "OPEN":
                return None
            pos, closed = self._engine_position(pid)
            held, pending = self._held(pid)
            lot = int(row["lot_size"]) or 1
            if closed or pos is None:
                target = 0
            else:
                base = int(row["paper_qty"]) or 1
                target = int(pos.quantity * min(1.0, self._bought(pid) / base) // lot) * lot
            need = held - pending - target
            if need <= 0:
                if held <= 0 and pending == 0:
                    self._refresh_position(pid, entry=False)
                return None
            if self._exit_failures.get(pid, 0) >= MAX_AUTO_EXIT_FAILURES:
                return None
            contract = Contract(row["exchange"], row["trading_symbol"], lot)
            ref = float(pos.current_option_price) if pos is not None else 0.0
            otype = self.runtime.get("live_exit_order_type")
            price = 0.0
            if otype == "LIMIT" and ref > 0:
                price = round_tick(ref * (1 - float(self.runtime.get("live_exit_limit_buffer_pct")) / 100.0), up=False)
            else:
                otype = "MARKET"
            sells = int(self._q("SELECT COUNT(*) AS n FROM live_orders WHERE position_id=? AND side='SELL'", (pid,))[0]["n"])
            tag = f"{self._base_tag(pid)}S{sells + 1}"  # new per attempt; a pending or unknown sell is already counted in `pending`
            req = OrderRequest(tag=tag, contract=contract, side="SELL", quantity=need, order_type=otype, price=price,
                               product=self.runtime.get("live_product_type"),
                               algo_id=str(self.runtime.get("live_algo_id")).strip())
            if not self._reserve_tag(tag, pid):
                return None  # this exact exit was already sent (maybe unknown); reconcile settles it
            if row["mode"] == "DRY":
                self._log_dry(pid, req, "dry-run exit: nothing was sent")
                self._refresh_position(pid, entry=False)
                return "DRY_RUN"
            if not self.broker.has_session():
                self._tag_state(tag, "RELEASED")
                self._err("LIVE_EXIT_NO_SESSION", f"Cannot exit {row['strike_symbol']}: no broker session. "
                          "Log in, or square off at the broker.", "CRITICAL")
                self._alert("live_exit_blocked", f"Exit pending for {row['strike_symbol']} but the broker session is gone. "
                            "Log in again or square off manually.", key=f"xs:{pid}", min_interval=300)
                return None
            return await self._send_and_confirm(pid, req, entry=False)

    async def retry_exit(self, pid: str) -> Optional[str]:
        self._exit_failures.pop(pid, None)
        self.audit("retry_exit", pid)
        return await self.sync_position(pid)

    # ------------------------------------------------------------------ reconcile
    async def reconcile(self) -> dict:
        """Refresh unsettled orders from the broker, then compare net positions. Alerts and halts on a difference."""
        out: dict = {"checked_orders": 0, "unknown_orders": [], "mismatches": [], "skipped": ""}
        if not self.broker.has_session():
            out["skipped"] = "no broker session"
            return out
        for r in self._q("SELECT * FROM live_orders WHERE mode='LIVE' AND status IN ('SENDING','NEW','OPEN','UNKNOWN')"):
            out["checked_orders"] += 1
            try:
                res = await self.broker.get_order(r["broker_order_id"]) if r["broker_order_id"] else await self.broker.find_order_by_tag(r["tag"])
            except BrokerAuthExpired:
                self._halt("BROKER_SESSION_EXPIRED", "Log in to the broker again.")
                out["skipped"] = "session expired"
                return out
            except BrokerError:
                res = None
            if res is None:
                if r["status"] in ("UNKNOWN", "SENDING"):
                    out["unknown_orders"].append(r["tag"])
                continue
            self._update_order(r["id"], res)
            if r["status"] in ("UNKNOWN", "SENDING"):
                self._tag_state(r["tag"], "DONE" if res.status in FINAL_STATES else "SENT")
            self._refresh_position(r["position_id"])
        if out["unknown_orders"]:
            self._halt("ORDER_UNKNOWN", f"{len(out['unknown_orders'])} order(s) cannot be found at the broker.")
        try:
            broker_net = await self.broker.net_positions()
        except BrokerAuthExpired:
            self._halt("BROKER_SESSION_EXPIRED", "Log in to the broker again.")
            out["skipped"] = "session expired"
            return out
        except BrokerError as exc:
            out["skipped"] = f"positions unavailable: {exc}"
            return out
        expected: dict[str, int] = {}
        for r in self._q("SELECT position_id, trading_symbol FROM live_positions WHERE mode='LIVE' AND (state IN ('ENTERING','OPEN') OR substr(closed_at,1,10)=?)", (_today(),)):
            held, _ = self._held(r["position_id"])
            expected[r["trading_symbol"]] = expected.get(r["trading_symbol"], 0) + held
        for sym, exp in expected.items():
            got = int(broker_net.get(sym, 0))
            if got != exp:
                out["mismatches"].append({"symbol": sym, "router": exp, "broker": got})
        if out["mismatches"]:
            text = "; ".join(f"{m['symbol']}: router {m['router']} vs broker {m['broker']}" for m in out["mismatches"])
            self._err("LIVE_POSITION_MISMATCH", text, "CRITICAL", {"mismatches": out["mismatches"]})
            self._alert("live_mismatch", f"Live position MISMATCH vs broker: {text}", key="mismatch", min_interval=300)
            if bool(self.runtime.get("live_halt_on_mismatch")):
                self._halt("POSITION_MISMATCH", text)
        return out

    async def resync_all(self) -> None:
        for r in self._q("SELECT position_id FROM live_positions WHERE state = 'OPEN'"):
            try:
                await self.sync_position(r["position_id"])
            except Exception as exc:
                self._err("LIVE_SYNC_FAILED", f"{type(exc).__name__}: {exc}", "ERROR")

    async def run_loop(self) -> None:
        """Retry pending exits and reconcile while anything is routed. Sleeps cheaply when routing is idle."""
        while True:
            try:
                busy = bool(self._tracked) or self._mode == LIVE
                if busy:
                    await self.resync_all()
                    if self._mode == LIVE or any(self._row(p) and self._row(p)["mode"] == "LIVE" for p in list(self._tracked)):
                        await self.reconcile()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._err("LIVE_LOOP_FAILED", f"{type(exc).__name__}: {exc}", "ERROR")
            try:
                await asyncio.sleep(float(self.runtime.get("live_reconcile_seconds")))
            except asyncio.CancelledError:
                raise

    # ------------------------------------------------------------------ read-only views
    def status(self) -> dict:
        positions = [dict(r) for r in self._q("SELECT * FROM live_positions ORDER BY opened_at DESC LIMIT 50")]
        for p in positions:
            held, pending = self._held(p["position_id"])
            p["held"], p["pending_sell"] = held, pending
        return {
            "mode": self._mode, "halted": self.halted, "broker": self.broker.name,
            "broker_session": self.broker.has_session(), "env_confirmed": self.env_confirmed(),
            "armed": bool(self._arm and time.monotonic() <= self._arm["expires"]),
            "preconditions": self.live_preconditions(check_session=True),
            "entries_today": self._count("side = 'BUY' AND status != 'BLOCKED'"),
            "orders_today": self._count("status != 'BLOCKED'"),
            "realized_today": self.realized_today(),
            "positions": positions,
        }

    def orders(self, limit: int = 100, day: Optional[str] = None) -> list[dict]:
        if day:
            rows = self._q("SELECT * FROM live_orders WHERE day = ? ORDER BY id DESC LIMIT ?", (day, int(limit)))
        else:
            rows = self._q("SELECT * FROM live_orders ORDER BY id DESC LIMIT ?", (int(limit),))
        return [dict(r) for r in rows]

    def audit_log(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM live_audit ORDER BY id DESC LIMIT ?", (int(limit),))]


def _exchange_segment(symbol: str) -> str:
    from app.services.strike_selector import option_exchange_segment
    return option_exchange_segment(symbol)


def _broker_segment(dhan_segment: str) -> str:
    return "BFO" if dhan_segment == "BSE_FNO" else "NFO"


_router: Optional[OrderRouter] = None


def set_router(r: Optional[OrderRouter]) -> None:
    global _router
    _router = r


def get_router() -> OrderRouter:
    if _router is None:
        raise RuntimeError("Order router is not initialised")
    return _router
