"""Definedge adapter against a mocked HTTP transport. Nothing here touches the network."""
import hashlib
import json
from datetime import date

import httpx
import pytest

from app.services import broker_definedge as bd
from app.services.broker_adapter import (
    CANCELED, COMPLETE, OPEN, REJECTED, BrokerAuthExpired, BrokerError, BrokerNotSent, BrokerRejected,
    BrokerTimeout, Contract, OrderRequest,
)

CONTRACT = Contract("NFO", "NIFTY27OCT2625000CE", 50)


def make(handler, key="KEY123"):
    b = bd.DefinedgeBroker(min_spacing=0)
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    b._session_key = key
    return b


def req(**kw):
    d = dict(tag="BBabc123B", contract=CONTRACT, side="BUY", quantity=100, order_type="LIMIT", price=151.5,
             algo_id="ALGO1")
    d.update(kw)
    return OrderRequest(**d)


@pytest.mark.asyncio
async def test_place_order_body_and_header():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers.get("authorization"), json.loads(request.content)
        return httpx.Response(200, json={"status": "SUCCESS", "order_id": "2610170001"})

    res = await make(handler).place_order(req())
    assert seen["url"] == bd.BASE_URL + "placeorder" and seen["auth"] == "KEY123"
    assert seen["body"] == {"exchange": "NFO", "order_type": "BUY", "price": 151.5, "price_type": "LIMIT",
                            "product_type": "INTRADAY", "quantity": 100, "tradingsymbol": CONTRACT.trading_symbol,
                            "algo_id": "ALGO1", "validity": "DAY", "remarks": "BBabc123B"}
    assert res.broker_order_id == "2610170001"


@pytest.mark.asyncio
async def test_market_order_sends_price_zero():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "SUCCESS", "order_id": "1"})

    await make(handler).place_order(req(order_type="MARKET", price=0.0, side="SELL"))
    assert seen["body"]["price"] == 0 and seen["body"]["price_type"] == "MARKET" and seen["body"]["order_type"] == "SELL"


@pytest.mark.asyncio
async def test_error_mapping():
    with pytest.raises(BrokerRejected, match="margin"):
        await make(lambda r: httpx.Response(200, json={"status": "ERROR", "message": "Insufficient margin"})).place_order(req())
    b = make(lambda r: httpx.Response(200, json={"status": "ERROR", "message": "Session Expired"}))
    with pytest.raises(BrokerAuthExpired):
        await b.place_order(req())
    assert not b.has_session()  # an expired key is dropped, not retried
    with pytest.raises(BrokerAuthExpired):
        await make(lambda r: httpx.Response(401, json={})).place_order(req())
    with pytest.raises(BrokerTimeout):  # answered without an order id: we cannot say it is not working
        await make(lambda r: httpx.Response(200, json={"status": "SUCCESS"})).place_order(req())
    with pytest.raises(BrokerTimeout):
        await make(lambda r: httpx.Response(502, json={"x": 1})).place_order(req())


@pytest.mark.asyncio
async def test_transport_failures_distinguish_sent_from_unknown():
    def refused(request):
        raise httpx.ConnectError("refused")

    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(BrokerNotSent):
        await make(refused).place_order(req())
    with pytest.raises(BrokerTimeout):
        await make(slow).place_order(req())


@pytest.mark.asyncio
async def test_no_session_never_calls_out():
    called = []
    b = make(lambda r: called.append(r) or httpx.Response(200, json={}), key="")
    with pytest.raises(BrokerAuthExpired):
        await b.place_order(req())
    assert called == []


def test_order_row_parsing_and_status_words():
    r = bd.parse_order_row({"orderid": "9", "order_status": "COMPLETE", "filled_qty": "100", "average_traded_price": "151.2"})
    assert (r.status, r.filled_qty, r.avg_price, r.broker_order_id) == (COMPLETE, 100, 151.2, "9")
    assert bd.parse_order_row({"status": "CANCELED"}).status == CANCELED
    assert bd.parse_order_row({"status": "REJECTED", "message": "rms"}).message == "rms"
    part = bd.parse_order_row({"status": "OPEN", "filled_qty": 50, "quantity": 100})
    assert (part.status, part.filled_qty) == (OPEN, 50)
    assert bd.parse_order_row({"status": "OPEN", "filled_qty": 100, "quantity": 100}).status == COMPLETE
    assert bd.parse_order_row({"status": "???"}).status == "UNKNOWN"


@pytest.mark.asyncio
async def test_find_by_tag_and_positions_and_cancel():
    orders = {"orders": [{"order_id": "1", "remarks": "other", "status": "OPEN"},
                         {"order_id": "2", "remarks": "BBabc123B", "status": "COMPLETE", "filled_qty": 100}]}
    positions = {"positions": [{"tradingsymbol": CONTRACT.trading_symbol, "net_quantity": "50"},
                               {"tradingsymbol": "X", "buy_quantity": 100, "sell_quantity": 40}]}
    cancelled = []

    def handler(request):
        path = request.url.path
        if path.endswith("/orders"):
            return httpx.Response(200, json=orders)
        if path.endswith("/positions"):
            return httpx.Response(200, json=positions)
        if "/cancel/" in path:
            cancelled.append(path)
            return httpx.Response(200, json={"status": "SUCCESS"})
        if "/order/" in path:
            return httpx.Response(200, json={"orders": [orders["orders"][1]]})
        return httpx.Response(404, json={})

    b = make(handler)
    assert (await b.find_order_by_tag("BBabc123B")).broker_order_id == "2"
    assert await b.find_order_by_tag("none") is None
    assert await b.net_positions() == {CONTRACT.trading_symbol: 50, "X": 60}
    await b.cancel_order("2")
    assert cancelled == ["/dart/v1/cancel/2"]
    assert (await b.get_order("2")).filled_qty == 100


@pytest.mark.asyncio
async def test_login_flow_keeps_key_in_memory(monkeypatch):
    monkeypatch.setenv("DEFINEDGE_API_TOKEN", "TOK")
    monkeypatch.setenv("DEFINEDGE_API_SECRET", "SEC")
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url), request.headers.get("api_secret"), request.headers.get("authorization")))
        if request.method == "GET":
            return httpx.Response(200, json={"otp_token": "OT"})
        body = json.loads(request.content)
        assert body == {"otp_token": "OT", "otp": "123456", "ac": hashlib.sha256(b"OT123456SEC").hexdigest()}
        return httpx.Response(200, json={"uid": "AB123", "actid": "AB123", "api_session_key": "NEWKEY", "susertoken": "w"})

    b = make(handler, key="")
    await b.login("123456")
    assert b.has_session() and b.masked_account() == "AB***"
    assert calls[0][1] == bd.LOGIN_URL + "login/TOK" and calls[0][2] == "SEC" and calls[0][3] is None
    b.clear_session()
    assert not b.has_session()


@pytest.mark.asyncio
async def test_login_needs_env_and_valid_totp(monkeypatch):
    b = make(lambda r: httpx.Response(200, json={}), key="")
    monkeypatch.delenv("DEFINEDGE_API_TOKEN", raising=False)
    with pytest.raises(BrokerError, match="DEFINEDGE_API_TOKEN"):
        await b.login("123456")
    monkeypatch.setenv("DEFINEDGE_API_TOKEN", "T")
    monkeypatch.setenv("DEFINEDGE_API_SECRET", "S")
    with pytest.raises(BrokerError, match="6-digit"):
        await b.login("12ab")


MASTER = "\n".join([
    # segment, token, symbol, trading_symbol, type, expiry, tick, lot, option_type, strike, exp10, mult
    "NFO,1,NIFTY,NIFTY27OCT2625000CE,OPTIDX,27102026,5,50,CE,25000,0,1,,1",
    "NFO,2,NIFTY,NIFTY27OCT2625000PE,OPTIDX,27102026,5,50,PE,25000,0,1,,1",
    "NFO,3,NIFTY,NIFTY27OCT26FUT,FUTIDX,27102026,5,50,,0,0,1,,1",
    "BFO,4,SENSEX,SENSEX27OCT2680000CE,OPTIDX,27102026,5,20,CE,80000,0,1,,1",
    "bad,row",
])


@pytest.mark.asyncio
async def test_contract_resolution_from_master():
    async def loader():
        return MASTER

    b = bd.DefinedgeBroker(min_spacing=0)
    b.master_loader = loader
    c = await b.resolve_contract(underlying="NIFTY", expiry="2026-10-27", strike=25000, option_type="CE", segment="NFO")
    assert c == Contract("NFO", "NIFTY27OCT2625000CE", 50)
    s = await b.resolve_contract(underlying="SENSEX", expiry="2026-10-27", strike=80000.0, option_type="CE", segment="BFO")
    assert s.lot_size == 20
    with pytest.raises(BrokerError, match="no contract"):
        await b.resolve_contract(underlying="NIFTY", expiry="2026-10-27", strike=25100, option_type="CE", segment="NFO")
    with pytest.raises(BrokerError, match="unreadable expiry"):
        await b.resolve_contract(underlying="NIFTY", expiry="soon", strike=25000, option_type="CE", segment="NFO")


@pytest.mark.asyncio
async def test_master_failure_fails_closed():
    async def loader():
        raise OSError("down")

    b = bd.DefinedgeBroker(min_spacing=0)
    b.master_loader = loader
    with pytest.raises(BrokerError, match="master unavailable"):
        await b.resolve_contract(underlying="NIFTY", expiry="2026-10-27", strike=25000, option_type="CE", segment="NFO")


def test_expiry_formats():
    assert bd.parse_expiry("27102026") == date(2026, 10, 27)
    assert bd.parse_expiry("27-Oct-2026") == date(2026, 10, 27)
    assert bd.parse_expiry("2026-10-27") == date(2026, 10, 27)
    assert bd.parse_expiry("") is None


def test_httpx_login_urls_are_not_logged():
    import logging
    rec = logging.LogRecord("httpx", logging.INFO, "", 0, 'HTTP Request: GET %s "200"',
                            (bd.LOGIN_URL + "login/SECRET_API_TOKEN",), None)
    f = bd._HideLoginUrls()
    assert f.filter(rec) is False
    ok = logging.LogRecord("httpx", logging.INFO, "", 0, 'HTTP Request: GET %s "200"', (bd.BASE_URL + "orders",), None)
    assert f.filter(ok) is True
