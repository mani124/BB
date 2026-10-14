import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel
from app.services.charges_calculator import calculate_option_trade_charges
from app.services.strategy_engine import Signal, is_setup5
from app.services.strike_selector import get_lot_size
from app.services import market_hours
from app.core.config import settings
from app.services.paper_models import *  # noqa: F401,F403
from app.services.paper_models import _now_stamp, _parse_iso, _signed_slip, _view_mode  # noqa: F401


class PaperPersistenceMixin:
    """Methods split out of PaperTradingEngine (no behaviour change)."""

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
