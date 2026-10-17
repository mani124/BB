"""Live order routing with a mocked broker. No test here reaches a real broker or the network."""
import asyncio

import pytest

from app.services import market_hours
from app.services.broker_adapter import (
    CANCELED, COMPLETE, OPEN, BrokerAuthExpired, BrokerError, BrokerNotSent, BrokerRejected, BrokerTimeout,
    Contract, OrderRequest, OrderResult,
)
from app.services.order_router import (
    CONFIRM_ENV, DRY_RUN, ENABLE_PHRASE, LIVE, OFF, OrderRouter, parse_allowed_setups, round_tick, setup_number,
)
from app.services.paper_trader import PaperTradingEngine
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation

CONTRACT = Contract("NFO", "NIFTY27OCT2625000CE", 50)


class FakeBroker:
    name = "fake"

    def __init__(self):
        self.session = True
        self.placed: list[OrderRequest] = []
        self.orders: dict[str, OrderResult] = {}
        self.tags: dict[str, str] = {}
        self.cancelled: list[str] = []
        self.net: dict[str, int] = {}
        self.fill = "full"  # full | none | partial
        self.place_exc: Exception | None = None
        self.hide_on_timeout = True
        self.resolve_exc: Exception | None = None
        self.contract = CONTRACT
        self.verify_exc: Exception | None = None

    def has_session(self):
        return self.session

    def clear_session(self):
        self.session = False

    async def verify_session(self):
        if self.verify_exc:
            raise self.verify_exc

    async def resolve_contract(self, **kw):
        if self.resolve_exc:
            raise self.resolve_exc
        return self.contract

    async def place_order(self, req):
        if self.place_exc is not None:
            exc = self.place_exc
            if isinstance(exc, BrokerTimeout) and not self.hide_on_timeout:
                self._store(req)  # the order reached the broker, only the answer was lost
            raise exc
        return self._store(req)

    def _store(self, req):
        oid = f"OID{len(self.placed) + 1}"
        self.placed.append(req)
        qty = {"full": req.quantity, "none": 0, "partial": (req.quantity // 100) * 50}[self.fill]
        status = COMPLETE if qty == req.quantity else OPEN
        price = req.price or 100.0
        res = OrderResult(broker_order_id=oid, status=status, filled_qty=qty, avg_price=price)
        self.orders[oid] = res
        self.tags[req.tag] = oid
        sign = 1 if req.side == "BUY" else -1
        self.net[req.contract.trading_symbol] = self.net.get(req.contract.trading_symbol, 0) + sign * qty
        return OrderResult(broker_order_id=oid, status="NEW")

    async def get_order(self, oid):
        return self.orders[oid]

    async def find_order_by_tag(self, tag):
        oid = self.tags.get(tag)
        return self.orders[oid] if oid else None

    async def cancel_order(self, oid):
        self.cancelled.append(oid)
        o = self.orders[oid]
        self.orders[oid] = OrderResult(oid, CANCELED, o.filled_qty, o.avg_price)

    async def net_positions(self):
        return dict(self.net)


class Alerts:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def __call__(self, event, text, dedupe_key=None, min_interval=0):
        self.sent.append((event, text))
        return True

    def events(self):
        return [e for e, _ in self.sent]


async def _nosleep(_):
    return None


def ctx(pid="P1", **over):
    d = dict(id=pid, symbol="NIFTY", option_type="CE", setup="Setup 5: Option Chart BB Scalp",
             strike_symbol="NIFTY 25000 CE", lots=2, qty=100, lot_size=50, entry=150.0, ask=150.0,
             strike=25000, expiry="2026-10-27", segment="NSE_FNO")
    d.update(over)
    return d


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIRM_ENV, "CONFIRMED")
    db = str(tmp_path / "t.db")
    engine = PaperTradingEngine(db_path=db)
    broker, alerts = FakeBroker(), Alerts()
    router = OrderRouter(db, engine.runtime, engine.telemetry, engine, broker, notify_fn=alerts, sleep=_nosleep)
    engine.runtime.set("live_allowed_setups", "5")
    engine.runtime.set("live_algo_id", "ALGO1")
    return engine, broker, alerts, router, db


async def go_live(router):
    router.arm()
    code = router._arm["code"]
    await router.enable_live(code, ENABLE_PHRASE)


def statuses(router):
    return [(o["side"], o["status"]) for o in reversed(router.orders())]


# ---------------------------------------------------------------- helpers
def test_helpers():
    assert setup_number("Setup 11: Filtered Option Chart Scalp") == 11
    assert parse_allowed_setups("5, 11;x") == {5, 11}
    assert round_tick(150 * 1.01) == 151.5
    assert round_tick(100.02, up=False) == 100.0


# ---------------------------------------------------------------- off and dry run
@pytest.mark.asyncio
async def test_off_does_nothing(env):
    engine, broker, alerts, router, _ = env
    assert router.mode == OFF
    assert await router.enter(ctx()) is None
    assert router.orders() == [] and broker.placed == []


@pytest.mark.asyncio
async def test_dry_run_logs_payload_and_sends_nothing(env):
    engine, broker, alerts, router, _ = env
    router.set_mode(DRY_RUN)
    assert await router.enter(ctx()) == "DRY_RUN"
    assert broker.placed == []
    (row,) = router.orders()
    assert row["status"] == "DRY_RUN" and row["mode"] == "DRY" and row["trading_symbol"] == CONTRACT.trading_symbol
    assert '"algo_id": "ALGO1"' in row["payload"] and row["price"] == 151.5  # ask 150 + 1% buffer on the tick
    # the dry-run position exits virtually, still without touching the broker
    await router.sync_position("P1")
    assert [o["status"] for o in router.orders()] == ["DRY_RUN", "DRY_RUN"]
    assert router._row("P1")["state"] == "CLOSED" and broker.placed == []


@pytest.mark.asyncio
async def test_demo_feed_never_routes(env):
    engine, broker, alerts, router, _ = env
    router.set_mode(DRY_RUN)

    class P:
        feed_mode = "demo"

    router.on_entry(P(), None)  # returns before touching the (absent) loop
    assert router.orders() == []


# ---------------------------------------------------------------- entry gates
@pytest.mark.parametrize("over,code", [
    (dict(setup="Setup 2: Walking the Bands (9 EMA)"), "SETUP_NOT_ALLOWED"),
    (dict(lots=3, qty=150), "LOTS_EXCEED"),
    (dict(ask=0), "MISSING_INPUT"),
    (dict(strike=None), "MISSING_INPUT"),
    (dict(expiry=None), "MISSING_INPUT"),
    (dict(qty=90), "MISSING_INPUT"),
    (dict(ask=3000.0, lots=2, qty=100), "VALUE_EXCEED"),
])
@pytest.mark.asyncio
async def test_entry_gates_block_and_log(env, over, code):
    engine, broker, alerts, router, _ = env
    router.set_mode(DRY_RUN)
    assert await router.enter(ctx(**over)) is None
    (row,) = router.orders()
    assert row["status"] == "BLOCKED" and row["message"].startswith(code)
    assert router._row("P1") is None


@pytest.mark.asyncio
async def test_kill_switch_loss_limit_and_halt_block_entries(env):
    engine, broker, alerts, router, _ = env
    router.set_mode(DRY_RUN)
    engine.set_kill_switch(True)
    await router.enter(ctx("K"))
    engine.set_kill_switch(False)
    engine.runtime.set("daily_loss_limit", 0)
    await router.enter(ctx("L"))  # no live limit and no general limit -> fail closed
    engine.runtime.set("daily_loss_limit", 24000)
    router._set_state("halted", "POSITION_MISMATCH")
    await router.enter(ctx("H"))
    msgs = [o["message"].split(":")[0] for o in reversed(router.orders())]
    assert msgs == ["KILL_SWITCH", "LOSS_LIMIT_UNSET", "HALTED"]


@pytest.mark.asyncio
async def test_entry_and_open_caps(env):
    engine, broker, alerts, router, _ = env
    router.set_mode(DRY_RUN)
    engine.runtime.set("live_max_open_positions", 1)
    assert await router.enter(ctx("A")) == "DRY_RUN"
    assert await router.enter(ctx("B")) is None
    assert router.orders()[0]["message"].startswith("OPEN_CAP")
    engine.runtime.set("live_max_open_positions", 5)
    engine.runtime.set("live_max_entries_per_day", 1)
    assert await router.enter(ctx("C")) is None
    assert router.orders()[0]["message"].startswith("ENTRY_CAP")
    engine.runtime.set("live_max_entries_per_day", 6)
    engine.runtime.set("live_max_orders_per_day", 1)
    assert await router.enter(ctx("D")) is None
    assert router.orders()[0]["message"].startswith("ORDER_CAP")


@pytest.mark.asyncio
async def test_contract_unresolved_and_lot_mismatch_fail_closed(env):
    engine, broker, alerts, router, _ = env
    router.set_mode(DRY_RUN)
    broker.resolve_exc = BrokerError("no contract")
    assert await router.enter(ctx("A")) is None
    broker.resolve_exc = None
    broker.contract = Contract("NFO", "X", 75)
    assert await router.enter(ctx("B")) is None
    assert [o["message"].split(":")[0] for o in reversed(router.orders())] == ["CONTRACT_UNRESOLVED", "LOT_MISMATCH"]


@pytest.mark.asyncio
async def test_outside_entry_window_blocks(env):
    from datetime import datetime
    engine, broker, alerts, router, _ = env
    router.set_mode(DRY_RUN)
    with market_hours.override_clock(datetime(2026, 10, 14, 15, 25, tzinfo=market_hours.IST)):
        assert await router.enter(ctx()) is None
    assert router.orders()[0]["message"].startswith("OUTSIDE_ENTRY_WINDOW")


# ---------------------------------------------------------------- going live
def test_set_mode_refuses_live(env):
    router = env[3]
    with pytest.raises(PermissionError):
        router.set_mode(LIVE)


def test_arm_needs_env_flag_and_settings(env, monkeypatch):
    engine, broker, alerts, router, _ = env
    monkeypatch.delenv(CONFIRM_ENV)
    with pytest.raises(PermissionError, match=CONFIRM_ENV):
        router.arm()
    monkeypatch.setenv(CONFIRM_ENV, "yes")
    with pytest.raises(PermissionError, match=CONFIRM_ENV):
        router.arm()
    monkeypatch.setenv(CONFIRM_ENV, "CONFIRMED")
    engine.runtime.set("live_algo_id", "")
    with pytest.raises(PermissionError, match="live_algo_id"):
        router.arm()


@pytest.mark.asyncio
async def test_enable_needs_code_phrase_and_session(env):
    engine, broker, alerts, router, _ = env
    with pytest.raises(PermissionError, match="Arm first"):
        await router.enable_live("123456", ENABLE_PHRASE)
    router.arm()
    code = router._arm["code"]
    with pytest.raises(PermissionError):
        await router.enable_live("000000" if code != "000000" else "111111", ENABLE_PHRASE)
    with pytest.raises(PermissionError):
        await router.enable_live(code, "yes")
    broker.verify_exc = BrokerAuthExpired("expired")
    with pytest.raises(PermissionError, match="not usable"):
        await router.enable_live(code, ENABLE_PHRASE)
    assert router.mode == OFF
    broker.verify_exc = None
    await router.enable_live(code, ENABLE_PHRASE)
    assert router.mode == LIVE and "live_on" in alerts.events()
    with pytest.raises(PermissionError):  # the code is single use
        await router.enable_live(code, ENABLE_PHRASE)


@pytest.mark.asyncio
async def test_code_expires_and_locks_after_wrong_tries(env, monkeypatch):
    engine, broker, alerts, router, _ = env
    router.arm()
    code = router._arm["code"]
    router._arm["expires"] -= 1000
    with pytest.raises(PermissionError, match="expired"):
        await router.enable_live(code, ENABLE_PHRASE)
    router.arm()
    for _ in range(3):
        with pytest.raises(PermissionError):
            await router.enable_live("bad", ENABLE_PHRASE)
    with pytest.raises(PermissionError, match="Too many|Arm first"):
        await router.enable_live(router._arm["code"] if router._arm else "x", ENABLE_PHRASE)


@pytest.mark.asyncio
async def test_live_never_survives_restart(env):
    engine, broker, alerts, router, db = env
    await go_live(router)
    again = OrderRouter(db, engine.runtime, engine.telemetry, engine, broker, notify_fn=alerts, sleep=_nosleep)
    assert again.mode == DRY_RUN
    assert any(a["action"] == "mode" and "restart" in a["detail"] for a in again.audit_log())


# ---------------------------------------------------------------- live entry
@pytest.mark.asyncio
async def test_live_entry_full_fill(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    assert await router.enter(ctx()) == COMPLETE
    (req,) = broker.placed
    assert (req.side, req.quantity, req.order_type, req.price, req.algo_id) == ("BUY", 100, "LIMIT", 151.5, "ALGO1")
    assert req.tag.startswith("BB") and req.tag.endswith("B")
    assert router._row("P1")["state"] == "OPEN" and router._held("P1") == (100, 0)
    assert "live_entry" in alerts.events()


@pytest.mark.asyncio
async def test_unfilled_entry_is_cancelled_and_fails(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.fill = "none"
    await router.enter(ctx())
    assert broker.cancelled == ["OID1"]
    assert router._row("P1")["state"] == "FAILED" and "live_entry_unfilled" in alerts.events()


@pytest.mark.asyncio
async def test_partial_entry_keeps_what_filled(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.fill = "partial"
    await router.enter(ctx())
    assert router._held("P1") == (50, 0) and router._row("P1")["state"] == "OPEN"
    assert "live_entry_partial" in alerts.events()


@pytest.mark.asyncio
async def test_rejected_entry_releases_tag_and_alerts(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.place_exc = BrokerRejected("margin")
    await router.enter(ctx())
    assert router._row("P1")["state"] == "FAILED" and "live_entry_failed" in alerts.events()
    assert router._q("SELECT * FROM order_tags") == []


@pytest.mark.asyncio
async def test_not_sent_releases_tag(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.place_exc = BrokerNotSent("refused")
    await router.enter(ctx())
    assert router._q("SELECT * FROM order_tags") == []


@pytest.mark.asyncio
async def test_timeout_found_by_tag_continues_without_resend(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.place_exc = BrokerTimeout("slow")
    broker.hide_on_timeout = False
    await router.enter(ctx())
    assert len(broker.placed) == 1  # looked up, never re-sent
    assert router._held("P1") == (100, 0) and not router.halted


@pytest.mark.asyncio
async def test_timeout_not_found_halts_and_never_resends(env):
    engine, broker, alerts, router, db = env
    await go_live(router)
    broker.place_exc = BrokerTimeout("slow")
    await router.enter(ctx())
    assert router.halted == "ORDER_UNKNOWN" and broker.placed == []
    (tag,) = router._q("SELECT tag, state FROM order_tags")
    assert tag["state"] == "UNKNOWN"
    # even after a restart, the same position cannot be sent a second time
    again = OrderRouter(db, engine.runtime, engine.telemetry, engine, broker, notify_fn=alerts, sleep=_nosleep)
    again._set_state("halted", "")
    broker.place_exc = None
    assert await again.enter(ctx()) is None
    assert again.orders()[0]["message"].startswith("DUPLICATE_BLOCKED") and broker.placed == []


@pytest.mark.asyncio
async def test_session_expiry_halts_entries(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.place_exc = BrokerAuthExpired("expired")
    await router.enter(ctx())
    assert router.halted == "BROKER_SESSION_EXPIRED" and "live_halt" in alerts.events()
    broker.place_exc = None
    assert await router.enter(ctx("P2")) is None  # halted


@pytest.mark.asyncio
async def test_no_session_blocks_live_entry(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.session = False
    assert await router.enter(ctx()) is None
    assert router.orders()[0]["message"].startswith("NO_BROKER_SESSION")


# ---------------------------------------------------------------- exits
@pytest.mark.asyncio
async def test_exit_sells_everything_even_when_everything_else_is_off(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    await router.enter(ctx())
    engine.set_kill_switch(True)
    router._set_state("halted", "POSITION_MISMATCH")
    router.set_mode(OFF)
    await router.sync_position("P1")  # the engine does not know P1 -> treated as closed
    sell = broker.placed[-1]
    assert (sell.side, sell.quantity, sell.order_type, sell.price) == ("SELL", 100, "MARKET", 0.0)
    assert router._row("P1")["state"] == "CLOSED" and "live_exit" in alerts.events()
    await router.sync_position("P1")
    assert len(broker.placed) == 2  # nothing left to sell


@pytest.mark.asyncio
async def test_exit_failure_alerts_and_stops_after_three(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    await router.enter(ctx())
    broker.place_exc = BrokerRejected("rms")
    for _ in range(5):
        await router.sync_position("P1")
    assert alerts.events().count("live_exit_failed") == 3
    assert router._held("P1") == (100, 0)
    broker.place_exc = None
    await router.retry_exit("P1")
    assert router._row("P1")["state"] == "CLOSED"


@pytest.mark.asyncio
async def test_exit_without_session_alerts_then_retries_after_login(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    await router.enter(ctx())
    broker.session = False
    await router.sync_position("P1")
    assert "live_exit_blocked" in alerts.events() and router._row("P1")["state"] == "OPEN"
    broker.session = True
    await router.resync_all()
    assert router._row("P1")["state"] == "CLOSED"


@pytest.mark.asyncio
async def test_limit_exit_unfilled_is_cancelled_then_resent(env):
    engine, broker, alerts, router, _ = env
    engine.runtime.set("live_exit_order_type", "LIMIT")
    await go_live(router)
    await router.enter(ctx())
    from types import SimpleNamespace
    router._engine_position = lambda pid: (SimpleNamespace(current_option_price=100.0, quantity=100), True)
    broker.fill = "none"
    await router.sync_position("P1")
    assert broker.cancelled and router._held("P1") == (100, 0)
    broker.fill = "full"
    await router.sync_position("P1")
    assert broker.placed[-1].order_type == "LIMIT" and router._row("P1")["state"] == "CLOSED"


# ---------------------------------------------------------------- reconcile
@pytest.mark.asyncio
async def test_reconcile_clean_then_mismatch_halts_and_resume_needs_clean(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    await router.enter(ctx())
    out = await router.reconcile()
    assert out["mismatches"] == [] and not router.halted
    broker.net[CONTRACT.trading_symbol] = 50  # someone sold half by hand
    out = await router.reconcile()
    assert out["mismatches"] == [{"symbol": CONTRACT.trading_symbol, "router": 100, "broker": 50}]
    assert router.halted == "POSITION_MISMATCH" and "live_mismatch" in alerts.events()
    res = await router.resume()
    assert res["halted"] == "POSITION_MISMATCH"  # still halted: the difference is still there
    broker.net[CONTRACT.trading_symbol] = 100
    res = await router.resume()
    assert res["halted"] == ""


@pytest.mark.asyncio
async def test_reconcile_settles_unknown_order(env):
    engine, broker, alerts, router, _ = env
    await go_live(router)
    broker.place_exc = BrokerTimeout("slow")
    await router.enter(ctx())
    assert router.halted == "ORDER_UNKNOWN"
    broker.place_exc = None
    broker._store(OrderRequest(tag=router._base_tag("P1") + "B", contract=CONTRACT, side="BUY", quantity=100,
                               order_type="LIMIT", price=151.5))
    out = await router.reconcile()
    assert out["unknown_orders"] == [] and router._held("P1") == (100, 0)


@pytest.mark.asyncio
async def test_reconcile_without_session_is_skipped(env):
    engine, broker, alerts, router, _ = env
    broker.session = False
    assert (await router.reconcile())["skipped"] == "no broker session"


# ---------------------------------------------------------------- the real engine drives the router
def _live_signal(sig_id="S1"):
    rec = OptionStrikeRecommendation(
        symbol="NIFTY", underlying_price=25000.0, option_type="CE", atm_strike=25000, recommended_strike=25000,
        strike_symbol="NIFTY 25000 CE", lot_size=50, risk=20.0, stop_loss=24980.0, target_1=25030.0,
        target_2=25050.0, estimated_option_entry=150.0, option_sl_pts=25.0, option_target_1_pts=37.5,
        option_target_2_pts=62.5, option_sl_price=125.0, option_target_1_price=187.5, option_target_2_price=212.5,
        option_security_id="777", expiry_date="2026-10-27", real_ask_price=150.0, real_bid_price=149.0,
        real_ltp=149.5, is_live_quote=True)
    return Signal(id=sig_id, symbol="NIFTY", timeframe="5m", setup_type=SetupType.SETUP_5_OPTION_BB,
                  option_type="CE", timestamp="11:00:00", entry_price=25000.0, stop_loss=24980.0,
                  target_1=25030.0, target_2=25050.0, strike_recommendation=rec, indicators_snapshot={},
                  rationale="t")


@pytest.mark.asyncio
async def test_engine_lifecycle_entry_partial_target_then_stop(env):
    engine, broker, alerts, router, _ = env
    router.bind_loop(asyncio.get_running_loop())
    engine.on_live_entry = router.on_entry
    engine.on_position_update = router.on_position_update
    await go_live(router)

    pos = engine.open_position_from_signal(_live_signal(), lots=2, feed_mode="live")
    assert pos is not None
    await asyncio.sleep(0.2)
    assert [(r.side, r.quantity) for r in broker.placed] == [("BUY", 100)]
    assert broker.placed[0].contract.trading_symbol == CONTRACT.trading_symbol

    # Target 1: the paper engine books one of two lots -> the router sells exactly that lot
    engine.update_market_prices({"NIFTY": 25031.0}, {"777": 190.0}, "live", {"777": 189.0})
    await asyncio.sleep(0.2)
    assert [(r.side, r.quantity) for r in broker.placed] == [("BUY", 100), ("SELL", 50)]
    assert router._held(pos.id) == (50, 0)

    # the same state again does not sell twice
    engine.update_market_prices({"NIFTY": 25032.0}, {"777": 191.0}, "live", {"777": 190.0})
    await asyncio.sleep(0.2)
    assert len(broker.placed) == 2

    # breakeven stop: the runner goes out and the routed position closes
    engine.update_market_prices({"NIFTY": 24990.0}, {"777": 140.0}, "live", {"777": 139.0})
    await asyncio.sleep(0.2)
    assert [(r.side, r.quantity) for r in broker.placed] == [("BUY", 100), ("SELL", 50), ("SELL", 50)]
    assert router._row(pos.id)["state"] == "CLOSED"
    assert broker.net[CONTRACT.trading_symbol] == 0


@pytest.mark.asyncio
async def test_engine_manual_close_and_kill_switch_exit(env):
    engine, broker, alerts, router, _ = env
    router.bind_loop(asyncio.get_running_loop())
    engine.on_live_entry = router.on_entry
    engine.on_position_update = router.on_position_update
    await go_live(router)
    pos = engine.open_position_from_signal(_live_signal("S2"), lots=2, feed_mode="live")
    await asyncio.sleep(0.2)
    engine.set_kill_switch(True)  # entries are now blocked...
    engine.close_position(pos.id, reason="KILL_SWITCH", real_bid_price=149.0, real_opt_price=149.5)
    await asyncio.sleep(0.2)  # ...but the exit still goes
    assert broker.placed[-1].side == "SELL" and router._row(pos.id)["state"] == "CLOSED"


@pytest.mark.asyncio
async def test_routing_off_leaves_paper_trading_untouched(env):
    engine, broker, alerts, router, _ = env
    engine.on_live_entry = router.on_entry
    engine.on_position_update = router.on_position_update
    pos = engine.open_position_from_signal(_live_signal("S3"), lots=2, feed_mode="live")
    assert pos is not None and pos.lots == 2
    engine.update_market_prices({"NIFTY": 25031.0}, {"777": 190.0}, "live", {"777": 189.0})
    engine.close_position(pos.id, reason="x", real_bid_price=189.0, real_opt_price=190.0)
    assert router.orders() == [] and broker.placed == []
    assert engine.get_portfolio().closed_trades[-1].status == "CLOSED"
