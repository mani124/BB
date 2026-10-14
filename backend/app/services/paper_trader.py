import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.strategy_engine import Signal
from app.services.strike_selector import get_lot_size
from app.services import market_hours
from app.core.config import settings

logger = logging.getLogger(__name__)

class PaperPosition(BaseModel):
    id: str
    signal_id: str
    symbol: str
    option_type: Literal["CE", "PE"]
    strike_symbol: str
    timeframe: str
    setup_type: str
    entry_time: str
    underlying_entry: float
    underlying_sl: float
    underlying_target_1: float
    underlying_target_2: float
    option_entry: float
    option_sl: float
    option_target_1: float
    option_target_2: float
    lot_size: int
    lots: int
    quantity: int
    current_underlying: float
    current_option_price: float
    pnl_points: float
    pnl_rupees: float
    status: Literal["OPEN", "TARGET_1", "TARGET_2", "STOPPED_OUT", "CLOSED"]
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None
    initial_lots: Optional[int] = None
    initial_quantity: Optional[int] = None
    booked_lots: int = 0
    booked_pnl_rupees: float = 0.0
    booked_slippage_cost: float = 0.0
    pending_spot_exit: Optional[str] = None
    pending_spot_tp1: bool = False
    option_security_id: Optional[str] = None
    feed_mode: str = "demo"  # "demo" or "live"
    theoretical_entry: float = 0.0
    entry_slippage: float = 0.0
    theoretical_exit: Optional[float] = None
    exit_slippage: float = 0.0
    total_slippage_cost: float = 0.0
    gross_pnl: float = 0.0
    total_charges: float = 0.0
    net_pnl: float = 0.0
    charges_breakdown: Optional[dict] = None
    # Full ISO datetimes (IST, with date). entry_time/exit_time stay HH:MM:SS for display.
    entry_datetime: Optional[str] = None
    exit_datetime: Optional[str] = None
    # Non-destructive quarantine: rows with a reason stay visible but are excluded from totals.
    quarantine_reason: Optional[str] = None
    # True when the entry price was modelled (no real ask/last from the exchange feed).
    entry_estimated: bool = False

class DailyPnl(BaseModel):
    date: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_pnl: float = 0.0
    total_charges: float = 0.0
    net_pnl: float = 0.0
    quarantined_excluded: int = 0

STALE_CARRYOVER = "STALE_CARRYOVER"
EOD_SQUARE_OFF = "EOD_SQUARE_OFF"

def _now_stamp() -> tuple[str, str]:
    """(HH:MM:SS display, ISO datetime with date) for the current IST instant."""
    n = market_hours.now_ist().replace(microsecond=0)
    return n.strftime("%H:%M:%S"), n.isoformat()

def _signed_slip(level: float, fill: float) -> float:
    """Slippage in points for a sell: positive = filled worse than the intended level,
    negative = price improvement (e.g. a gap through a target)."""
    return round(float(level) - float(fill), 2)

def _view_mode(mode: Optional[str]) -> Optional[str]:
    """Portfolio views are either demo or live. Every non-demo scan state (live, stale,
    error, closed) shows the live book, so positions never vanish when the market closes."""
    if not mode:
        return None
    return "demo" if mode == "demo" else "live"

def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=market_hours.IST)

class PaperPortfolio(BaseModel):
    active_positions: list[PaperPosition] = []
    closed_trades: list[PaperPosition] = []
    auto_trade_enabled: bool = True
    default_lots: int = 2
    max_risk_per_trade: float = 4000.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    win_rate_pct: float = 0.0
    total_trades_count: int = 0
    winning_trades_count: int = 0
    losing_trades_count: int = 0
    total_gross_pnl: float = 0.0
    total_slippage_cost: float = 0.0
    avg_slippage_points: float = 0.0
    total_charges: float = 0.0
    total_net_pnl: float = 0.0

class PaperTradingEngine:
    """Manages paper trading execution, position monitoring, and analytics."""

    def __init__(self, db_path: Optional[str] = None):
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids: set[str] = set()
        self.storage = None
        self.on_position_opened: Optional[Callable[[PaperPosition], Any]] = None
        self._write_queue: Optional[asyncio.Queue] = None
        self._writer_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._portfolio_generation: int = 0
        self._pending_errors: list[Exception] = []
        if db_path is not None:
            from app.services.paper_storage import PaperStorage
            self.storage = PaperStorage(db_path)
            self._load_from_storage()

    def _execute_storage_op(self, op: str, arg: Any) -> None:
        if not self.storage:
            return
        if op == "upsert":
            self.storage.upsert_position(arg)
        elif op == "batch_upsert":
            self.storage.batch_upsert_positions(arg)
        elif op == "add_signal":
            sig_id, ts = arg
            self.storage.add_processed_signal(sig_id, ts)
        elif op == "save_setting":
            k, v = arg
            self.storage.save_setting(k, v)
        elif op == "clear_all":
            self.storage.clear_all()

    async def _persistence_worker(self) -> None:
        while True:
            try:
                if self._write_queue is None:
                    break
                item = await self._write_queue.get()
                if item is None:
                    self._write_queue.task_done()
                    break
                op, arg, gen, fut = item
                # F2: Reject in-flight scan writes from older generations
                if gen < self._portfolio_generation and op != "clear_all":
                    if fut and not fut.done():
                        fut.set_result(False)
                    self._write_queue.task_done()
                    continue

                try:
                    await asyncio.to_thread(self._execute_storage_op, op, arg)
                    if fut and not fut.done():
                        fut.set_result(True)
                except Exception as exc:
                    logger.error(f"Persistence worker error executing {op}: {exc}")
                    if fut and not fut.done():
                        fut.set_exception(exc)
                    else:
                        self._pending_errors.append(exc)
                finally:
                    self._write_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in persistence worker loop: {e}")

    def _enqueue_write(
        self,
        op: str,
        arg: Any,
        generation: Optional[int] = None,
        future: Optional[asyncio.Future] = None
    ) -> None:
        if not self.storage:
            if future and not future.done():
                future.set_result(True)
            return

        gen = generation if generation is not None else self._portfolio_generation
        if generation is not None and generation < self._portfolio_generation and op != "clear_all":
            if future and not future.done():
                future.set_result(False)
            return

        item = (op, arg, gen, future)

        if self._write_queue is not None:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is self._loop or (running_loop and self._loop is None):
                self._write_queue.put_nowait(item)
            elif self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._write_queue.put_nowait, item)
            else:
                try:
                    self._execute_storage_op(op, arg)
                    if future and not future.done():
                        future.set_result(True)
                except Exception as e:
                    self._pending_errors.append(e)
                    if future and not future.done():
                        future.set_exception(e)
                    raise
        else:
            try:
                self._execute_storage_op(op, arg)
                if future and not future.done():
                    future.set_result(True)
            except Exception as e:
                self._pending_errors.append(e)
                if future and not future.done():
                    future.set_exception(e)
                raise

    async def start_persistence_worker(self) -> None:
        if not self.storage:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        self._loop = loop
        if self._write_queue is None:
            self._write_queue = asyncio.Queue()
        if self._writer_task is None or self._writer_task.done():
            self._writer_task = loop.create_task(self._persistence_worker())

    async def flush(self) -> None:
        if self._write_queue is not None:
            await self._write_queue.join()
        if self._pending_errors:
            err = self._pending_errors.pop(0)
            raise err

    async def stop_persistence_worker(self) -> None:
        if self._write_queue is not None:
            try:
                await self.flush()
            except Exception:
                logger.warning("Error during flush in stop_persistence_worker", exc_info=True)
            finally:
                await self._write_queue.put(None)
                if self._writer_task and not self._writer_task.done():
                    try:
                        await self._writer_task
                    except asyncio.CancelledError:
                        pass
                self._writer_task = None
                self._write_queue = None

    def _load_from_storage(self):
        if not self.storage:
            return
        active, closed = self.storage.load_all_positions()
        self._portfolio.active_positions = active
        self._portfolio.closed_trades = closed
        self._processed_signal_ids = self.storage.load_processed_signals()

        saved_auto = self.storage.load_setting("auto_trade_enabled")
        if saved_auto is not None:
            self._portfolio.auto_trade_enabled = (saved_auto.lower() == "true")

        saved_lots = self.storage.load_setting("default_lots")
        if saved_lots is not None:
            try:
                self._portfolio.default_lots = int(saved_lots)
            except ValueError:
                pass

        saved_risk = self.storage.load_setting("max_risk_per_trade")
        if saved_risk is not None:
            try:
                self._portfolio.max_risk_per_trade = float(saved_risk)
            except ValueError:
                pass

        self.flag_stale_carryover()
        self._recalculate_metrics()

    def get_portfolio(self, mode: Optional[str] = None) -> PaperPortfolio:
        self._recalculate_metrics()
        mode = _view_mode(mode)
        if not mode:
            return self._portfolio

        active = [p for p in self._portfolio.active_positions if getattr(p, "feed_mode", "demo") == mode]
        all_closed = [p for p in self._portfolio.closed_trades if getattr(p, "feed_mode", "demo") == mode]
        closed = [p for p in all_closed if not p.quarantine_reason]
        closed_pnl = sum(p.pnl_rupees for p in closed)
        active_booked_pnl = sum(p.booked_pnl_rupees for p in active)
        realized = round(closed_pnl + active_booked_pnl, 2)
        unrealized = round(sum(round(p.pnl_points * p.quantity, 2) for p in active), 2)
        total = round(realized + unrealized, 2)
        total_trades = len(closed)
        winning = sum(1 for p in closed if p.pnl_rupees > 0)
        losing = sum(1 for p in closed if p.pnl_rupees <= 0)
        win_rate = round((winning / total_trades) * 100, 1) if total_trades > 0 else 0.0

        total_gross = sum(getattr(p, "gross_pnl", 0.0) or p.pnl_rupees for p in closed)
        total_charges = sum(getattr(p, "total_charges", 0.0) for p in closed)
        total_net = sum(getattr(p, "net_pnl", 0.0) for p in closed)
        total_slip_cost = sum(getattr(p, "total_slippage_cost", 0.0) for p in closed)
        avg_slip_pts = (
            sum((getattr(p, "entry_slippage", 0.0) + getattr(p, "exit_slippage", 0.0)) for p in closed) / total_trades
            if total_trades > 0 else 0.0
        )

        return PaperPortfolio(
            active_positions=active,
            closed_trades=all_closed,
            auto_trade_enabled=self._portfolio.auto_trade_enabled,
            default_lots=self._portfolio.default_lots,
            max_risk_per_trade=self._portfolio.max_risk_per_trade,
            total_realized_pnl=realized,
            total_unrealized_pnl=unrealized,
            total_pnl=total,
            win_rate_pct=win_rate,
            total_trades_count=total_trades,
            winning_trades_count=winning,
            losing_trades_count=losing,
            total_gross_pnl=round(total_gross, 2),
            total_slippage_cost=round(total_slip_cost, 2),
            avg_slippage_points=round(avg_slip_pts, 2),
            total_charges=round(total_charges, 2),
            total_net_pnl=round(total_net, 2)
        )

    def get_daily_pnl(self, mode: Optional[str] = None) -> list[DailyPnl]:
        """P1-7: realized P&L per IST exit date (newest first). Quarantined rows are
        excluded from the figures and only counted in ``quarantined_excluded``."""
        mode = _view_mode(mode)
        days: dict[str, DailyPnl] = {}
        for p in self._portfolio.closed_trades:
            if mode is not None and getattr(p, "feed_mode", "demo") != mode:
                continue
            stamp = _parse_iso(p.exit_datetime) or _parse_iso(p.entry_datetime)
            key = stamp.date().isoformat() if stamp else "unknown"
            day = days.setdefault(key, DailyPnl(date=key))
            if p.quarantine_reason:
                day.quarantined_excluded += 1
                continue
            day.trades += 1
            if p.pnl_rupees > 0:
                day.wins += 1
            elif p.pnl_rupees < 0:
                day.losses += 1
            day.gross_pnl = round(day.gross_pnl + (p.gross_pnl or p.pnl_rupees), 2)
            day.total_charges = round(day.total_charges + p.total_charges, 2)
            day.net_pnl = round(day.net_pnl + p.net_pnl, 2)
        return sorted(days.values(), key=lambda d: d.date, reverse=True)

    def set_auto_trade(self, enabled: bool):
        self._portfolio.auto_trade_enabled = enabled
        self._enqueue_write("save_setting", ("auto_trade_enabled", str(enabled)))

    def set_default_lots(self, lots: int):
        self._portfolio.default_lots = max(1, lots)
        self._enqueue_write("save_setting", ("default_lots", str(self._portfolio.default_lots)))

    def set_max_risk_per_trade(self, amount: float):
        self._portfolio.max_risk_per_trade = max(500.0, float(amount))
        self._enqueue_write("save_setting", ("max_risk_per_trade", str(self._portfolio.max_risk_per_trade)))

    async def reset(self) -> None:
        self._portfolio_generation += 1
        self._portfolio = PaperPortfolio()
        self._processed_signal_ids.clear()
        if self._write_queue is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = self._loop or asyncio.get_event_loop()
            fut = loop.create_future()
            self._enqueue_write("clear_all", None, generation=self._portfolio_generation, future=fut)
            await fut
        elif self.storage:
            self.storage.clear_all()

    def reset_sync(self) -> None:
        if self._loop and self._loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self.reset(), self._loop)
            fut.result(timeout=10.0)
        else:
            self._portfolio_generation += 1
            self._portfolio = PaperPortfolio()
            self._processed_signal_ids.clear()
            if self.storage:
                self.storage.clear_all()

    def reset_portfolio(self) -> None:
        self.reset_sync()

    def open_position_from_signal(
        self,
        signal: Signal,
        lots: Optional[int] = None,
        feed_mode: str = "demo"
    ) -> Optional[PaperPosition]:
        # Avoid duplicate trades on same signal ID
        if signal.id in self._processed_signal_ids:
            return None

        if feed_mode not in ("live", "demo"):
            logger.info("Skipping trade opening for feed_mode '%s' (not live or demo)", feed_mode)
            return None

        # P0-1: no new live entries outside the exchange session or after the entry cutoff.
        # (demo mode runs on synthetic offline data and is not tied to exchange hours)
        if feed_mode == "live" and not market_hours.is_entry_allowed():
            logger.info("Entry skipped for %s: outside entry window (session closed or past cutoff)", signal.symbol)
            return None

        # P0-2: exposure guards (one position per contract, per stock+side, plus cooldown)
        block = self._exposure_block_reason(signal)
        if block:
            logger.info("Entry blocked for %s %s: %s", signal.symbol, signal.option_type, block)
            self._processed_signal_ids.add(signal.id)
            return None

        # Check re-entry gate: prevent consecutive stop-out churn in the same chop box
        last_closed = next(
            (p for p in reversed(self._portfolio.closed_trades) if p.symbol == signal.symbol and p.option_type == signal.option_type and not p.quarantine_reason),
            None
        )
        if last_closed and last_closed.status == "STOPPED_OUT":
            is_s5 = (
                signal.setup_type in ("Setup 5: Option Chart BB Scalp", "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB")
                or "Setup 5" in str(signal.setup_type)
            )
            if is_s5:
                failed_peak = last_closed.option_entry
                opt_entry = signal.strike_recommendation.estimated_option_entry
                if opt_entry <= failed_peak:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} Setup 5: option entry {opt_entry} <= previous failed option price {failed_peak} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    return None
            elif signal.option_type == "CE":
                failed_peak = last_closed.underlying_entry
                if signal.entry_price <= failed_peak:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} CE: entry {signal.entry_price} <= previous failed high {failed_peak} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    return None
            elif signal.option_type == "PE":
                failed_trough = last_closed.underlying_entry
                if signal.entry_price >= failed_trough:
                    logger.info(
                        f"Re-entry blocked for {signal.symbol} PE: entry {signal.entry_price} >= previous failed low {failed_trough} (Chop box protection)"
                    )
                    self._processed_signal_ids.add(signal.id)
                    return None

        rec = signal.strike_recommendation
        if feed_mode == "live":
            sec_id = getattr(rec, "option_security_id", None)
            is_live = getattr(rec, "is_live_quote", False)
            real_ask = float(getattr(rec, "real_ask_price", 0.0) or 0.0)
            real_ltp = float(getattr(rec, "real_ltp", 0.0) or 0.0)
            if not sec_id or not str(sec_id).strip() or not (is_live or real_ask > 0 or real_ltp > 0):
                logger.info(
                    f"Live position entry skipped for {signal.symbol}: contract unresolved or missing usable live option quote"
                )
                self._processed_signal_ids.add(signal.id)
                return None

            # P1-3: reject stale or untradeable quotes (frozen last trade, wide/one-sided market).
            quote_block = self._quote_block_reason(rec)
            if quote_block:
                logger.info("Live position entry skipped for %s: %s", signal.symbol, quote_block)
                self._processed_signal_ids.add(signal.id)
                return None

        lot_size = rec.lot_size

        risk_per_unit = max(0.1, abs(rec.estimated_option_entry - rec.option_sl_price))
        risk_per_lot = risk_per_unit * lot_size

        target_lots = lots if lots is not None else self._portfolio.default_lots
        lots_to_trade = target_lots

        if self._portfolio.max_risk_per_trade > 0 and risk_per_lot > 0:
            allowed_lots = int(self._portfolio.max_risk_per_trade // risk_per_lot)
            if allowed_lots < 1:
                logger.info(
                    f"Trade skipped for {signal.symbol}: risk per lot {risk_per_lot:.1f} exceeds max risk cap {self._portfolio.max_risk_per_trade:.1f}"
                )
                self._processed_signal_ids.add(signal.id)
                return None
            lots_to_trade = min(target_lots, allowed_lots)

        self._processed_signal_ids.add(signal.id)
        qty = lot_size * lots_to_trade

        pos_id = f"POS_{signal.symbol}_{signal.option_type}_{int(market_hours.now_ist().timestamp())}_{uuid.uuid4().hex[:6]}"
        rec = signal.strike_recommendation

        p_signal = float(rec.estimated_option_entry)
        is_s5 = (
            signal.setup_type in ("Setup 5: Option Chart BB Scalp", "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB")
            or "Setup 5" in str(signal.setup_type)
        )
        entry_estimated = False
        if getattr(rec, "real_ask_price", 0.0) is not None and float(rec.real_ask_price or 0.0) > 0:
            p_fill_entry = float(rec.real_ask_price)
        elif not is_s5 and getattr(rec, "real_ltp", 0.0) is not None and float(rec.real_ltp or 0.0) > 0:
            p_fill_entry = round(float(rec.real_ltp) * 1.001, 2)
        else:
            p_fill_entry = float(p_signal)
            entry_estimated = True

        entry_slippage = max(0.0, round(p_fill_entry - p_signal, 2))
        init_slip_cost = round(entry_slippage * qty, 2)

        pos = PaperPosition(
            id=pos_id,
            signal_id=signal.id,
            symbol=signal.symbol,
            option_type=signal.option_type,
            strike_symbol=rec.strike_symbol,
            timeframe=signal.timeframe,
            setup_type=signal.setup_type.value if hasattr(signal.setup_type, "value") else str(signal.setup_type),
            entry_time=_now_stamp()[0],
            entry_datetime=_now_stamp()[1],
            underlying_entry=signal.entry_price,
            underlying_sl=signal.stop_loss,
            underlying_target_1=signal.target_1,
            underlying_target_2=signal.target_2,
            option_entry=round(p_fill_entry, 2),
            option_sl=rec.option_sl_price,
            option_target_1=rec.option_target_1_price,
            option_target_2=rec.option_target_2_price,
            lot_size=lot_size,
            lots=lots_to_trade,
            quantity=qty,
            initial_lots=lots_to_trade,
            initial_quantity=qty,
            booked_lots=0,
            booked_pnl_rupees=0.0,
            current_underlying=signal.entry_price,
            current_option_price=round(p_fill_entry, 2),
            pnl_points=0.0,
            pnl_rupees=0.0,
            status="OPEN",
            option_security_id=getattr(rec, "option_security_id", None),
            feed_mode=feed_mode,
            theoretical_entry=round(p_signal, 2),
            entry_slippage=entry_slippage,
            theoretical_exit=None,
            exit_slippage=0.0,
            total_slippage_cost=init_slip_cost,
            gross_pnl=0.0,
            total_charges=0.0,
            net_pnl=0.0,
            charges_breakdown=None,
            entry_estimated=entry_estimated,
        )

        self._portfolio.active_positions.append(pos)
        self._recalculate_metrics()
        self._persist_entry(pos, signal.id)
        if self.on_position_opened:
            try:
                res = self.on_position_opened(pos)
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        pass
            except Exception as e:
                logger.warning(f"Error executing on_position_opened callback: {e}")
        return pos

    def _persist_entry(self, pos: PaperPosition, signal_id: str) -> None:
        """P1-4: write the new position and its processed-signal id in ONE synchronous
        transaction, so a crash or --reload between the two can never let the same signal
        open a second position after restart. Later updates still go through the queue."""
        if not self.storage:
            return
        created = market_hours.now_ist().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.storage.record_entry(pos, signal_id, created)
        except Exception as exc:
            logger.error("Atomic entry persistence failed for %s: %s", pos.id, exc)
            self._pending_errors.append(exc)

    @staticmethod
    def _quote_block_reason(rec) -> Optional[str]:
        """P1-3: None if the live quote behind a recommendation is fresh and tradeable."""
        if getattr(rec, "lot_size_known", True) is False:
            return "lot size unknown (guessed default); refusing to size a position"
        max_age = float(getattr(settings, "MAX_QUOTE_AGE_SECONDS", 0) or 0)
        age = getattr(rec, "quote_age_s", None)
        if max_age > 0 and age is not None and float(age) > max_age:
            return f"quote is {float(age):.0f}s old (limit {max_age:.0f}s)"
        ask = float(getattr(rec, "real_ask_price", 0.0) or 0.0)
        bid = float(getattr(rec, "real_bid_price", 0.0) or 0.0)
        max_spread = float(getattr(settings, "MAX_ENTRY_SPREAD_PCT", 0) or 0)
        if max_spread > 0 and ask > 0 and bid > 0:
            if ask < bid:
                return f"crossed market (bid {bid} > ask {ask})"
            spread_pct = (ask - bid) / ask * 100.0
            if spread_pct > max_spread:
                return f"spread {spread_pct:.1f}% exceeds {max_spread:.0f}% (bid {bid}, ask {ask})"
        return None

    @staticmethod
    def _contract_key(security_id: Optional[str], strike_symbol: Optional[str]) -> Optional[str]:
        if security_id and str(security_id).strip():
            return f"id:{str(security_id).strip()}"
        if strike_symbol and str(strike_symbol).strip():
            return f"sym:{str(strike_symbol).strip()}"
        return None

    def _exposure_block_reason(self, signal: Signal) -> Optional[str]:
        """P0-2: returns why a new entry must be refused, or None if it may proceed."""
        rec = signal.strike_recommendation
        key = self._contract_key(getattr(rec, "option_security_id", None), getattr(rec, "strike_symbol", None))
        for p in self._portfolio.active_positions:
            if key and self._contract_key(p.option_security_id, p.strike_symbol) == key:
                return f"contract {key} already has an open position"
            if p.symbol == signal.symbol and p.option_type == signal.option_type:
                return f"{p.symbol} {p.option_type} already has an open position"

        # P1-7: portfolio-level caps (0 disables a cap)
        max_open = int(getattr(settings, "MAX_OPEN_POSITIONS", 0) or 0)
        if max_open > 0 and len(self._portfolio.active_positions) >= max_open:
            return f"max open positions reached ({max_open})"

        max_notional = float(getattr(settings, "MAX_OPEN_NOTIONAL", 0) or 0)
        if max_notional > 0:
            open_notional = sum(p.option_entry * p.quantity for p in self._portfolio.active_positions)
            lots = self._portfolio.default_lots
            new_notional = float(getattr(rec, "estimated_option_entry", 0.0) or 0.0) * int(getattr(rec, "lot_size", 0) or 0) * max(1, lots)
            if open_notional + new_notional > max_notional:
                return f"open premium notional would exceed {max_notional:,.0f}"

        max_per_day = int(getattr(settings, "MAX_ENTRIES_PER_SYMBOL_PER_DAY", 0) or 0)
        if max_per_day > 0:
            today = market_hours.now_ist().date()
            entered = 0
            for p in self._portfolio.active_positions + self._portfolio.closed_trades:
                if p.symbol != signal.symbol or p.quarantine_reason:
                    continue
                ed = _parse_iso(p.entry_datetime)
                if ed is not None and ed.date() == today:
                    entered += 1
            if entered >= max_per_day:
                return f"{signal.symbol} already had {entered} entries today (limit {max_per_day})"

        cooldown = int(getattr(settings, "REENTRY_COOLDOWN_SECONDS", 0) or 0)
        if cooldown > 0:
            now = market_hours.now_ist()
            for p in reversed(self._portfolio.closed_trades):
                if p.symbol != signal.symbol or p.option_type != signal.option_type or p.quarantine_reason:
                    continue
                exited = _parse_iso(p.exit_datetime)
                if exited and timedelta(0) <= (now - exited) < timedelta(seconds=cooldown):
                    return f"cooldown ({cooldown}s) after exit on {p.symbol} {p.option_type}"
        return None

    def flag_stale_carryover(self) -> list[PaperPosition]:
        """P0-5: positions still open from a previous IST date can't be valid intraday
        positions. Close them out as STALE_CARRYOVER (no repricing) and quarantine them
        so they are excluded from performance stats."""
        today = market_hours.now_ist().date()
        stale = []
        for pos in list(self._portfolio.active_positions):
            entered = _parse_iso(pos.entry_datetime)
            if entered is None or entered.date() >= today:
                continue
            _, now_iso = _now_stamp()
            pos.status = "CLOSED"
            pos.exit_reason = STALE_CARRYOVER
            pos.exit_time = _now_stamp()[0]
            pos.exit_datetime = now_iso
            pos.quarantine_reason = STALE_CARRYOVER
            self._portfolio.active_positions.remove(pos)
            self._portfolio.closed_trades.append(pos)
            self._enqueue_write("upsert", pos)
            stale.append(pos)
        if stale:
            logger.warning("Flagged %d stale carried-over position(s) as %s", len(stale), STALE_CARRYOVER)
            self._recalculate_metrics()
        return stale

    def square_off_if_due(self, feed_mode: Optional[str] = "live") -> list[PaperPosition]:
        """P0-5: close open positions once the EOD square-off time is reached."""
        if not market_hours.is_square_off_due():
            return []
        closed = []
        for pos in list(self._portfolio.active_positions):
            if feed_mode is not None and getattr(pos, "feed_mode", "demo") != feed_mode:
                continue
            res = self.close_position(pos.id, reason=EOD_SQUARE_OFF)
            if res:
                closed.append(res)
        return closed

    def on_signals_cycle(self, signals: list[Signal], feed_mode: str = "demo"):
        """Automatically open paper positions if auto-trade is enabled."""
        if not self._portfolio.auto_trade_enabled:
            return
        if feed_mode not in ("live", "demo"):
            return

        for sig in signals:
            if not getattr(sig, "is_confirmed", True):
                continue
            if sig.id not in self._processed_signal_ids:
                # Open position for new signals
                self.open_position_from_signal(sig, feed_mode=feed_mode)

    def _finalize_closed_position(
        self,
        pos: PaperPosition,
        theoretical_exit: float,
        status: Literal["OPEN", "TARGET_1", "TARGET_2", "STOPPED_OUT", "CLOSED"],
        reason: str,
        exit_time: str,
        real_bid_price: Optional[float] = None,
        real_opt_price: Optional[float] = None,
    ):
        # 1. Determine fill price P_fill_exit
        if real_bid_price is not None and float(real_bid_price) > 0:
            p_fill_exit = float(real_bid_price)
        elif real_opt_price is not None and float(real_opt_price) > 0:
            opt_val = float(real_opt_price)
            if opt_val < float(theoretical_exit):
                p_fill_exit = opt_val
            else:
                p_fill_exit = round(opt_val * 0.999, 2)
        elif pos.feed_mode == "live":
            p_fill_exit = float(pos.current_option_price)
            if "(Modeled" not in reason:
                reason = f"{reason} (Modeled: Last Price)"
        else:
            p_fill_exit = float(theoretical_exit)

        # 2. Exit slippage: signed. Positive = worse than the intended level; negative =
        # price improvement (e.g. a gap through a target). A fill far beyond the level is
        # labelled as a gap so it is not mistaken for a clean level hit.
        exit_slippage = _signed_slip(theoretical_exit, p_fill_exit)
        gap_pct = float(getattr(settings, "GAP_EXIT_PCT", 0) or 0)
        level = float(theoretical_exit)
        if gap_pct > 0 and level > 0 and "(Gap" not in reason and status in ("STOPPED_OUT", "TARGET_2"):
            move_pct = abs(p_fill_exit - level) / level * 100.0
            if move_pct >= gap_pct:
                reason = f"{reason} (Gap Exit: filled {p_fill_exit:.2f} vs level {level:.2f})"

        # 3. Update position state and P&L
        pos.status = status
        pos.exit_time = exit_time
        pos.exit_datetime = _now_stamp()[1]
        pos.exit_reason = reason
        pos.theoretical_exit = round(float(theoretical_exit), 2)
        pos.exit_slippage = exit_slippage
        pos.current_option_price = round(p_fill_exit, 2)
        pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
        runner_pnl = round(pos.pnl_points * pos.quantity, 2)
        pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)

        # 4. Total slippage cost
        init_qty = pos.initial_quantity if (pos.initial_quantity and pos.initial_quantity > 0) else pos.quantity
        runner_qty = pos.quantity
        entry_slip_cost = round(pos.entry_slippage * init_qty, 2)
        runner_slip_cost = round(pos.exit_slippage * runner_qty, 2)
        booked_slip_cost = round(getattr(pos, "booked_slippage_cost", 0.0), 2)
        pos.total_slippage_cost = round(entry_slip_cost + booked_slip_cost + runner_slip_cost, 2)

        # 5. Charges calculation
        orders_count = 3 if pos.booked_lots > 0 else 2
        sell_price = max(0.0, round(pos.option_entry + (pos.pnl_rupees / init_qty), 2)) if init_qty > 0 else pos.current_option_price
        breakdown = calculate_option_trade_charges(
            buy_price=pos.option_entry,
            sell_price=sell_price,
            quantity=init_qty,
            orders_count=orders_count,
        )

        pos.gross_pnl = round(pos.pnl_rupees, 2)
        pos.total_charges = breakdown.total_charges
        pos.net_pnl = round(pos.gross_pnl - pos.total_charges, 2)
        pos.charges_breakdown = breakdown.model_dump()

    def update_market_prices(
        self,
        price_map: dict[str, float],
        option_price_map: Optional[dict[str, float]] = None,
        feed_mode: Optional[str] = None,
        option_bid_map: Optional[dict[str, float]] = None,
    ):
        """Update active positions with current underlying prices and live option prices from Dhan."""
        delta = 0.55
        now_str = _now_stamp()[0]
        still_active = []
        changed_active: list[PaperPosition] = []

        for pos in self._portfolio.active_positions:
            orig_state = (
                pos.current_underlying, pos.current_option_price, pos.pnl_points,
                pos.pnl_rupees, pos.status, pos.lots, pos.quantity, pos.underlying_sl,
                pos.option_sl, getattr(pos, "pending_spot_exit", None),
                getattr(pos, "pending_spot_tp1", False)
            )

            if feed_mode is not None and getattr(pos, "feed_mode", "demo") != feed_mode:
                still_active.append(pos)
                continue

            curr_spot = price_map.get(pos.symbol)
            if curr_spot is not None:
                pos.current_underlying = round(curr_spot, 2)

            is_opt_chart_setup = (
                pos.setup_type in ("Setup 5: Option Chart BB Scalp", "BB_EXPANSION_SCALP", "SETUP_5_OPTION_BB")
                or "Setup 5" in str(pos.setup_type)
            )

            # Check if live option quote is directly provided from Dhan (NSE_FNO)
            real_opt_price = None
            if option_price_map:
                if pos.option_security_id:
                    real_opt_price = option_price_map.get(str(pos.option_security_id)) or option_price_map.get(pos.option_security_id)
                if real_opt_price is None:
                    real_opt_price = option_price_map.get(pos.id) or option_price_map.get(pos.strike_symbol)

            real_bid_price = None
            if option_bid_map:
                real_bid_price = option_bid_map.get(pos.id)
                if real_bid_price is None and pos.option_security_id:
                    real_bid_price = option_bid_map.get(str(pos.option_security_id)) or option_bid_map.get(pos.option_security_id)
                if real_bid_price is None and pos.strike_symbol:
                    real_bid_price = option_bid_map.get(pos.strike_symbol)

            if real_opt_price is not None and float(real_opt_price) > 0:
                pos.current_option_price = round(float(real_opt_price), 2)
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif pos.feed_mode == "live" or pos.option_security_id:
                # Live contract: keep last known real price, do not synthesize fake delta
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif is_opt_chart_setup:
                # Setup 5: Option chart scalp - maintain current option price if no new tick
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 2)
            elif curr_spot is not None and pos.feed_mode == "demo":
                # Fallback to delta estimation only for demo/offline signals lacking option_security_id
                if pos.option_type == "CE":
                    spot_move = curr_spot - pos.underlying_entry
                    est_opt = max(0.5, pos.option_entry + (spot_move * delta))
                else:
                    spot_move = pos.underlying_entry - curr_spot
                    est_opt = max(0.5, pos.option_entry + (spot_move * delta))
                pos.current_option_price = round(est_opt, 1)
                pos.pnl_points = round(pos.current_option_price - pos.option_entry, 1)
            else:
                still_active.append(pos)
                continue

            has_fresh_quote = (
                (real_bid_price is not None and float(real_bid_price) > 0)
                or (real_opt_price is not None and float(real_opt_price) > 0)
            )

            # Check if pending spot exit can now execute with fresh quote
            if getattr(pos, "pending_spot_exit", None) and has_fresh_quote:
                pending_reason = pos.pending_spot_exit
                theo_exit = pos.option_sl if ("Stop-Loss" in pending_reason or "SL" in pending_reason) else pos.option_target_2
                status_to_set = "STOPPED_OUT" if ("Stop-Loss" in pending_reason or "SL" in pending_reason) else "TARGET_2"
                self._finalize_closed_position(
                    pos=pos,
                    theoretical_exit=theo_exit,
                    status=status_to_set,
                    reason=pending_reason,
                    exit_time=now_str,
                    real_bid_price=real_bid_price,
                    real_opt_price=real_opt_price,
                )
                self._portfolio.closed_trades.append(pos)
                self._enqueue_write("upsert", pos)
                continue

            # --- SETUP 5: EXITS BASED EXCLUSIVELY ON OPTION CHARTS ---
            if is_opt_chart_setup:
                if pos.current_option_price <= pos.option_sl:
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_sl,
                        status="STOPPED_OUT",
                        reason=reason,
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                elif pos.current_option_price >= pos.option_target_2:
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_target_2,
                        status="TARGET_2",
                        reason="Target 2 (1:2.5) Hit",
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                elif pos.current_option_price >= pos.option_target_1 and pos.status == "OPEN":
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else pos.current_option_price
                        tp1_slippage = _signed_slip(pos.option_target_1, tp1_fill)
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    pos.option_sl = pos.option_entry
                    self._enqueue_write("upsert", pos)

                still_active.append(pos)
                continue

            # --- SETUPS 1-4 & 6-8: EXITS BASED ON UNDERLYING SPOT OR OPTION LEVELS ---
            if pos.option_type == "CE":
                # Check SL
                if (curr_spot is not None and curr_spot <= pos.underlying_sl) or pos.current_option_price <= pos.option_sl:
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = reason
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_sl,
                        status="STOPPED_OUT",
                        reason=reason,
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot >= pos.underlying_target_2) or pos.current_option_price >= pos.option_target_2:
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = "Target 2 (1:2.5) Hit"
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_target_2,
                        status="TARGET_2",
                        reason="Target 2 (1:2.5) Hit",
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 1
                hit_ce_tp1 = (
                    ((curr_spot is not None and curr_spot >= pos.underlying_target_1) or pos.current_option_price >= pos.option_target_1)
                    and pos.status == "OPEN"
                ) or getattr(pos, "pending_spot_tp1", False)

                if hit_ce_tp1:
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_tp1 = True
                        still_active.append(pos)
                        continue
                    pos.pending_spot_tp1 = False
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else (real_opt_price if (real_opt_price and real_opt_price > 0) else pos.current_option_price)
                        tp1_slippage = _signed_slip(pos.option_target_1, tp1_fill)
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            else:  # PE
                # Check SL
                if (curr_spot is not None and curr_spot >= pos.underlying_sl) or pos.current_option_price <= pos.option_sl:
                    is_breakeven = (pos.status == "TARGET_1")
                    reason = "Breakeven Trailed SL Hit" if is_breakeven else "Stop-Loss Hit"
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = reason
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_sl,
                        status="STOPPED_OUT",
                        reason=reason,
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 2
                elif (curr_spot is not None and curr_spot <= pos.underlying_target_2) or pos.current_option_price >= pos.option_target_2:
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_exit = "Target 2 (1:2.5) Hit"
                        still_active.append(pos)
                        continue
                    self._finalize_closed_position(
                        pos=pos,
                        theoretical_exit=pos.option_target_2,
                        status="TARGET_2",
                        reason="Target 2 (1:2.5) Hit",
                        exit_time=now_str,
                        real_bid_price=real_bid_price,
                        real_opt_price=real_opt_price,
                    )
                    self._portfolio.closed_trades.append(pos)
                    self._enqueue_write("upsert", pos)
                    continue

                # Check Target 1
                hit_pe_tp1 = (
                    ((curr_spot is not None and curr_spot <= pos.underlying_target_1) or pos.current_option_price >= pos.option_target_1)
                    and pos.status == "OPEN"
                ) or getattr(pos, "pending_spot_tp1", False)

                if hit_pe_tp1:
                    if pos.feed_mode == "live" and not has_fresh_quote:
                        pos.pending_spot_tp1 = True
                        still_active.append(pos)
                        continue
                    pos.pending_spot_tp1 = False
                    pos.status = "TARGET_1"
                    if pos.lots >= 2:
                        book_lots = pos.lots // 2
                        book_qty = book_lots * pos.lot_size
                        tp1_fill = real_bid_price if (real_bid_price and real_bid_price > 0) else (real_opt_price if (real_opt_price and real_opt_price > 0) else pos.current_option_price)
                        tp1_slippage = _signed_slip(pos.option_target_1, tp1_fill)
                        tp1_slip_cost = round(tp1_slippage * book_qty, 2)
                        pos.booked_slippage_cost = round(getattr(pos, "booked_slippage_cost", 0.0) + tp1_slip_cost, 2)
                        book_pnl = round((tp1_fill - pos.option_entry) * book_qty, 2)
                        pos.booked_lots += book_lots
                        pos.booked_pnl_rupees = round(pos.booked_pnl_rupees + book_pnl, 2)
                        pos.lots -= book_lots
                        pos.quantity -= book_qty
                    pos.underlying_sl = pos.underlying_entry
                    pos.option_sl = pos.option_entry

            runner_pnl = round(pos.pnl_points * pos.quantity, 2)
            pos.pnl_rupees = round(pos.booked_pnl_rupees + runner_pnl, 2)
            new_state = (
                pos.current_underlying, pos.current_option_price, pos.pnl_points,
                pos.pnl_rupees, pos.status, pos.lots, pos.quantity, pos.underlying_sl,
                pos.option_sl, getattr(pos, "pending_spot_exit", None),
                getattr(pos, "pending_spot_tp1", False)
            )
            if orig_state != new_state:
                changed_active.append(pos)
            still_active.append(pos)

        self._portfolio.active_positions = still_active
        self._recalculate_metrics()
        if changed_active:
            self._enqueue_write("batch_upsert", list(changed_active))

    def close_position(
        self,
        position_id: str,
        reason: str = "MANUAL_EXIT",
        exit_price: Optional[float] = None,
        real_bid_price: Optional[float] = None,
        real_opt_price: Optional[float] = None,
    ) -> Optional[PaperPosition]:
        for i, pos in enumerate(self._portfolio.active_positions):
            if pos.id == position_id:
                # F8: In live mode, derive theoretical exit strictly from server-owned observations
                if pos.feed_mode == "live":
                    if real_opt_price is not None and float(real_opt_price) > 0:
                        theo_exit = float(real_opt_price)
                    elif real_bid_price is not None and float(real_bid_price) > 0:
                        theo_exit = float(real_bid_price)
                    else:
                        theo_exit = pos.current_option_price
                else:
                    if exit_price is not None and exit_price > 0:
                        theo_exit = exit_price
                    elif real_opt_price is not None and float(real_opt_price) > 0:
                        theo_exit = float(real_opt_price)
                    else:
                        theo_exit = pos.current_option_price
                self._finalize_closed_position(
                    pos=pos,
                    theoretical_exit=theo_exit,
                    status="CLOSED",
                    reason=reason,
                    exit_time=_now_stamp()[0],
                    real_bid_price=real_bid_price,
                    real_opt_price=real_opt_price,
                )
                closed = self._portfolio.active_positions.pop(i)
                self._portfolio.closed_trades.append(closed)
                self._recalculate_metrics()
                self._enqueue_write("upsert", closed)
                return closed
        return None

    def _recalculate_metrics(self):
        counted = [p for p in self._portfolio.closed_trades if not p.quarantine_reason]
        closed_pnl = sum(p.pnl_rupees for p in counted)
        active_booked_pnl = sum(p.booked_pnl_rupees for p in self._portfolio.active_positions)
        realized = closed_pnl + active_booked_pnl
        unrealized = sum(round(p.pnl_points * p.quantity, 2) for p in self._portfolio.active_positions)

        wins = sum(1 for p in counted if p.pnl_rupees > 0)
        losses = sum(1 for p in counted if p.pnl_rupees < 0)
        total_closed = len(counted)

        self._portfolio.total_realized_pnl = round(realized, 2)
        self._portfolio.total_unrealized_pnl = round(unrealized, 2)
        self._portfolio.total_pnl = round(realized + unrealized, 2)
        self._portfolio.winning_trades_count = wins
        self._portfolio.losing_trades_count = losses
        self._portfolio.total_trades_count = total_closed
        self._portfolio.win_rate_pct = round((wins / total_closed * 100.0) if total_closed > 0 else 0.0, 1)

        total_gross = sum(getattr(p, "gross_pnl", 0.0) or p.pnl_rupees for p in counted)
        total_charges = sum(getattr(p, "total_charges", 0.0) for p in counted)
        total_net = sum(getattr(p, "net_pnl", 0.0) for p in counted)
        total_slip_cost = sum(getattr(p, "total_slippage_cost", 0.0) for p in counted)
        avg_slip_pts = (
            sum((getattr(p, "entry_slippage", 0.0) + getattr(p, "exit_slippage", 0.0)) for p in counted) / total_closed
            if total_closed > 0 else 0.0
        )

        self._portfolio.total_gross_pnl = round(total_gross, 2)
        self._portfolio.total_charges = round(total_charges, 2)
        self._portfolio.total_net_pnl = round(total_net, 2)
        self._portfolio.total_slippage_cost = round(total_slip_cost, 2)
        self._portfolio.avg_slippage_points = round(avg_slip_pts, 2)

from app.core.config import settings
paper_trader = PaperTradingEngine(db_path=settings.DB_PATH)
