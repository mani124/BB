"""Dhan 429 handling: shared cooldown, shared/negative chain cache, scanner failure back-off, daily counter."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import readiness
from app.services.dhan_client import DhanClient
from app.services.scanner_worker import ScannerWorker
from app.services.universe_manager import UniverseManager


def _resp(status, body=None):
    r = MagicMock()
    r.status_code = status
    r.text = ""
    r.json.return_value = body or {}
    return r


CHAIN_OK = _resp(200, {"data": {"oc": {"25000.000000": {"ce": {"last_price": 1.0}}}}})


@pytest.mark.asyncio
async def test_429_counts_and_starts_shared_cooldown_without_retrying_chain():
    c = DhanClient(min_spacing=0)
    post = AsyncMock(return_value=_resp(429))
    with patch("httpx.AsyncClient.post", post):
        assert await c.fetch_option_chain("c", "t", 13, "IDX_I", "2026-10-22") == {}
        assert post.await_count == 1  # no inline retry
        st = c.rate_limit_status()
        assert st["today"] == 1 and st["cooldown_s"] > 0
        # While cooling down, other chains and expiry lists are not even requested.
        assert await c.fetch_option_chain("c", "t", 25, "IDX_I", "2026-10-22") == {}
        assert await c.fetch_expiry_list("c", "t", 25, "IDX_I") == []
        assert post.await_count == 1
    await c.close()


@pytest.mark.asyncio
async def test_cooldown_doubles_on_consecutive_429s_and_resets_on_success():
    c = DhanClient(min_spacing=0)
    assert c._note_rate_limited("x") == 2.0
    assert c._note_rate_limited("x") == 4.0
    for _ in range(10):
        length = c._note_rate_limited("x")
    assert length == 30.0
    assert c.rate_limit_status()["today"] == 12
    c._cooldown_until = 0.0
    c._note_ok()
    assert c._note_rate_limited("x") == 2.0


@pytest.mark.asyncio
async def test_cooldown_wait_does_not_hold_the_pacing_lock():
    c = DhanClient(min_spacing=0)
    c._cooldown_until = asyncio.get_running_loop().time() + 0.3
    waiter = asyncio.create_task(c._throttle())
    await asyncio.sleep(0.05)
    assert not c._pace_lock.locked()
    await waiter


@pytest.mark.asyncio
async def test_chain_cached_shared_and_in_flight_deduped():
    c = DhanClient(min_spacing=0)
    post = AsyncMock(return_value=CHAIN_OK)
    with patch("httpx.AsyncClient.post", post):
        a, b = await asyncio.gather(*[c.fetch_option_chain("c", "t", 13, "IDX_I", "2026-10-22") for _ in range(2)])
        assert a == b and a
        again = await c.fetch_option_chain("c", "t", 13, "IDX_I", "2026-10-22")  # e.g. the earnings engine
        assert again == a
        assert post.await_count == 1
    await c.close()


@pytest.mark.asyncio
async def test_failed_chain_is_cached_briefly():
    c = DhanClient(min_spacing=0)
    post = AsyncMock(return_value=_resp(500))
    with patch("httpx.AsyncClient.post", post):
        await c.fetch_option_chain("c", "t", 13, "IDX_I", "2026-10-22")
        await c.fetch_option_chain("c", "t", 13, "IDX_I", "2026-10-22")
        assert post.await_count == 1
    await c.close()


def _worker(dhan):
    return ScannerWorker(universe_mgr=UniverseManager(), dhan_client=dhan)


class _Inst:
    symbol, security_id, exchange_segment = "NIFTY 50", "13", "IDX_I"


@pytest.mark.asyncio
async def test_scanner_does_not_retry_failed_chain_every_cycle_and_keeps_expiry():
    dhan = MagicMock()
    dhan.fetch_expiry_list = AsyncMock(return_value=["2099-01-01"])
    dhan.fetch_option_chain = AsyncMock(return_value={})
    w = _worker(dhan)
    for _ in range(5):
        expiry, oc = await w.get_or_fetch_option_chain("c", "t", _Inst())
        assert oc == {}
    assert dhan.fetch_option_chain.await_count == 1
    assert dhan.fetch_expiry_list.await_count == 1  # expiry kept on an empty chain
    assert expiry == "2099-01-01"


@pytest.mark.asyncio
async def test_scanner_does_not_retry_failed_expiry_list_every_cycle():
    dhan = MagicMock()
    dhan.fetch_expiry_list = AsyncMock(return_value=[])
    dhan.fetch_option_chain = AsyncMock(return_value={})
    w = _worker(dhan)
    for _ in range(4):
        assert await w.get_or_fetch_option_chain("c", "t", _Inst()) == ("", {})
    assert dhan.fetch_expiry_list.await_count == 1


@pytest.mark.asyncio
async def test_scanner_retries_after_the_failure_window():
    dhan = MagicMock()
    dhan.fetch_expiry_list = AsyncMock(return_value=["2099-01-01"])
    dhan.fetch_option_chain = AsyncMock(return_value={})
    w = _worker(dhan)
    await w.get_or_fetch_option_chain("c", "t", _Inst())
    w._chain_fail_until["NIFTY 50"] = 0.0
    await w.get_or_fetch_option_chain("c", "t", _Inst())
    assert dhan.fetch_option_chain.await_count == 2


def test_readiness_warns_on_many_429s():
    base = dict(has_dhan_login=True, feed_live=True)
    low = {c.key: c for c in readiness.run_checks(**base, rate_limit={"today": 3})}
    high = {c.key: c for c in readiness.run_checks(**base, rate_limit={"today": 1400})}
    assert low["dhan_rate_limit"].status == readiness.OK
    assert high["dhan_rate_limit"].status == readiness.WARN and "1400" in high["dhan_rate_limit"].detail
