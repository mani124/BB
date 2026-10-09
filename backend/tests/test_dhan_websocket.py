import asyncio
import struct
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.services.dhan_websocket import DhanWebSocketManager
from app.services.dhan_packet_codec import (
    encode_login_packet,
    encode_subscription_packet,
)


@pytest.mark.asyncio
async def test_websocket_manager_lifecycle():
    ticks_received = []

    async def on_tick(tick):
        ticks_received.append(tick)

    mgr = DhanWebSocketManager(on_tick_callback=on_tick)
    assert mgr.is_connected is False
    assert mgr.status == "DISCONNECTED"

    # Mock connection and tick delivery
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(
        side_effect=[
            b"\x0b\x00\x53\x00",  # Login Ack (Code 11)
            asyncio.CancelledError(),  # Stop loop
        ]
    )
    mock_ws.close = AsyncMock()

    with patch("websockets.connect", return_value=mock_ws) as mock_connect:
        await mgr.connect("1000000000", "TEST_TOKEN")
        mock_connect.assert_called_with(mgr.url, ping_interval=None)
        assert mgr.is_connected is True
        assert mgr.status == "CONNECTED"
        await mgr.subscribe([(1, 1330), (2, 44608)])
        assert mock_ws.send.called
        # Check login packet was sent first
        first_call_arg = mock_ws.send.call_args_list[0][0][0]
        assert first_call_arg == encode_login_packet("1000000000", "TEST_TOKEN")

        await mgr.disconnect()
        assert mgr.is_connected is False
        assert mgr.status == "DISCONNECTED"


@pytest.mark.asyncio
async def test_websocket_reader_dispatches_ticks():
    ticks_received = []

    async def on_tick(tick):
        ticks_received.append(tick)

    # 16-byte Ticker packet: Code 2, Seg 1, Len 16, SecId 1330, LTT 1728500000, LTP 25050.25
    ticker_bytes = struct.pack("<BBHiif", 2, 1, 16, 1330, 1728500000, 25050.25)
    # 50-byte Quote packet: Code 4, Seg 2, Len 50, SecId 44608, LTT 1728500000, LTP 160.5, LTQ 100, VWAP 158.0, Vol 250000, Close 152
    quote_bytes = (
        struct.pack(
            "<BBHiififiiiii",
            4, 2, 50, 44608, 1728500000, 160.5, 100, 158.0, 250000, 150, 165, 148, 152
        )
        + b"\x00" * 6
    )
    # Malformed packet
    malformed_bytes = b"\x02\x00"

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(
        side_effect=[
            b"\x0b\x00\x53\x00",  # Login Ack (Code 11)
            ticker_bytes,         # Ticker
            malformed_bytes,      # Should be dropped cleanly without error
            quote_bytes,          # Quote
            asyncio.CancelledError(),  # End reader loop
        ]
    )
    mock_ws.close = AsyncMock()

    mgr = DhanWebSocketManager(on_tick_callback=on_tick)

    with patch("websockets.connect", return_value=mock_ws):
        await mgr.connect("1000000000", "TEST_TOKEN")
        # Give reader loop a brief moment to process frames
        await asyncio.sleep(0.05)

        assert len(ticks_received) == 2
        assert ticks_received[0]["response_code"] == 2
        assert ticks_received[0]["security_id"] == 1330
        assert pytest.approx(ticks_received[0]["ltp"], 0.01) == 25050.25

        assert ticks_received[1]["response_code"] == 4
        assert ticks_received[1]["security_id"] == 44608
        assert pytest.approx(ticks_received[1]["ltp"], 0.01) == 160.5
        assert ticks_received[1]["volume"] == 250000

        await mgr.disconnect()


@pytest.mark.asyncio
async def test_websocket_batch_subscription():
    mgr = DhanWebSocketManager()
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(side_effect=[asyncio.CancelledError()])
    mock_ws.close = AsyncMock()

    with patch("websockets.connect", return_value=mock_ws):
        await mgr.connect("1000000000", "TEST_TOKEN")

        # Create 150 instruments to test 100-scrip chunk boundary
        instruments = [(1, i) for i in range(1, 151)]
        await mgr.subscribe(instruments, mode=2)

        # Login packet (call 0) + 2 subscription packets (call 1: 100 items, call 2: 50 items)
        assert mock_ws.send.call_count == 3
        assert len(mgr.subscribed_instruments) == 150

        await mgr.disconnect()


@pytest.mark.asyncio
async def test_websocket_auto_reconnect_and_resubscribe():
    first_ws = AsyncMock()
    first_ws.send = AsyncMock()
    first_ws.recv = AsyncMock(side_effect=[
        b"\x0b\x00\x53\x00",
        ConnectionResetError("Socket reset by peer"),
    ])
    first_ws.close = AsyncMock()

    second_ws = AsyncMock()
    second_ws.send = AsyncMock()
    second_ws.recv = AsyncMock(side_effect=[
        b"\x0b\x00\x53\x00",
        asyncio.CancelledError(),
    ])
    second_ws.close = AsyncMock()

    connect_calls = [first_ws, second_ws]

    def mock_connect(*args, **kwargs):
        if connect_calls:
            return connect_calls.pop(0)
        return second_ws

    mgr = DhanWebSocketManager(backoff_delays=(0.01, 0.02))

    with patch("websockets.connect", side_effect=mock_connect):
        await mgr.connect("1000000000", "TEST_TOKEN")
        await mgr.subscribe([(1, 1330), (2, 44608)])

        # Allow time for first connection failure and auto-reconnect
        await asyncio.sleep(0.08)

        # Second websocket should have been connected and re-subscribed
        assert mgr.is_connected is True
        assert mgr.status == "CONNECTED"
        assert second_ws.send.call_count >= 2  # Login + Re-subscribe

        await mgr.disconnect()
        assert mgr.status == "DISCONNECTED"


@pytest.mark.asyncio
async def test_websocket_clean_shutdown():
    mgr = DhanWebSocketManager()
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(side_effect=[asyncio.CancelledError()])
    mock_ws.close = AsyncMock()

    with patch("websockets.connect", return_value=mock_ws):
        await mgr.connect("1000000000", "TEST_TOKEN")
        # Idempotent disconnect
        await mgr.disconnect()
        await mgr.disconnect()

        assert mgr.is_connected is False
        assert mgr.status == "DISCONNECTED"


def test_websocket_zero_token_persistence():
    mgr = DhanWebSocketManager()
    status = mgr.get_status()
    assert "access_token" not in status
    assert "client_id" not in status
    assert status["status"] == "DISCONNECTED"
    assert status["is_connected"] is False
    assert status["subscribed_count"] == 0

    rep = repr(mgr)
    assert "token" not in rep.lower() or "secret" not in rep.lower()


@pytest.mark.asyncio
async def test_websocket_code_50_triggers_reconnect():
    code_50_bytes = struct.pack("<BBHii", 50, 0, 10, 0, 805)  # Disconnect alert

    first_ws = AsyncMock()
    first_ws.send = AsyncMock()
    first_ws.recv = AsyncMock(side_effect=[
        b"\x0b\x00\x53\x00",
        code_50_bytes,
    ])
    first_ws.close = AsyncMock()

    second_ws = AsyncMock()
    second_ws.send = AsyncMock()
    second_ws.recv = AsyncMock(side_effect=[
        b"\x0b\x00\x53\x00",
        asyncio.CancelledError(),
    ])
    second_ws.close = AsyncMock()

    connect_calls = [first_ws, second_ws]

    def mock_connect(*args, **kwargs):
        if connect_calls:
            return connect_calls.pop(0)
        return second_ws

    mgr = DhanWebSocketManager(backoff_delays=(0.01, 0.02))

    with patch("websockets.connect", side_effect=mock_connect):
        await mgr.connect("1000000000", "TEST_TOKEN")
        await asyncio.sleep(0.06)

        assert mgr.is_connected is True
        assert mgr.status == "CONNECTED"
        assert second_ws.send.called

        await mgr.disconnect()


@pytest.mark.asyncio
async def test_websocket_sync_callback_and_callback_exception():
    received = []

    def sync_on_tick(tick):
        received.append(tick)
        if len(received) == 1:
            raise RuntimeError("Callback crash test")

    mgr = DhanWebSocketManager(on_tick_callback=sync_on_tick)

    t1 = struct.pack("<BBHiif", 2, 1, 16, 1330, 1728500000, 25000.0)
    t2 = struct.pack("<BBHiif", 2, 1, 16, 1330, 1728500001, 25010.0)

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(side_effect=[
        b"\x0b\x00\x53\x00",
        t1,
        t2,
        asyncio.CancelledError(),
    ])
    mock_ws.close = AsyncMock()

    with patch("websockets.connect", return_value=mock_ws):
        await mgr.connect("1000000000", "TEST_TOKEN")
        await asyncio.sleep(0.05)

        # Both ticks should have reached callback despite first one raising exception
        assert len(received) == 2
        assert received[0]["ltp"] == 25000.0
        assert received[1]["ltp"] == 25010.0

        await mgr.disconnect()


@pytest.mark.asyncio
async def test_websocket_subscribe_before_connect_and_unsubscribe():
    mgr = DhanWebSocketManager()
    await mgr.subscribe([(1, 1330), (2, 44608)])
    assert (1, 1330) in mgr.subscribed_instruments
    assert len(mgr.subscribed_instruments) == 2

    await mgr.unsubscribe([(1, 1330)])
    assert (1, 1330) not in mgr.subscribed_instruments
    assert len(mgr.subscribed_instruments) == 1

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(side_effect=[asyncio.CancelledError()])
    mock_ws.close = AsyncMock()

    with patch("websockets.connect", return_value=mock_ws):
        await mgr.connect("1000000000", "TEST_TOKEN")
        # Should have sent login packet AND subscription packet for remaining instrument (2, 44608)
        assert mock_ws.send.call_count == 2
        await mgr.disconnect()

