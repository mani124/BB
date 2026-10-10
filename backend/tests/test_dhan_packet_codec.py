import json
import pytest
import struct
from app.services.dhan_packet_codec import (
    encode_login_packet,
    encode_subscription_packet,
    encode_subscription_json,
    decode_packet,
    segment_to_str,
    segment_to_int,
)

def test_encode_login_packet():
    packet = encode_login_packet("1000000000", "my_sample_access_token")
    assert len(packet) == 83
    req_code, msg_len = struct.unpack_from("<HH", packet, 0)
    assert req_code == 11
    assert msg_len == 83


def test_encode_subscription_json():
    instruments = [(1, 1333), (0, 13)]
    payload_str = encode_subscription_json(instruments, request_code=15)
    data = json.loads(payload_str)
    assert data["RequestCode"] == 15
    assert data["InstrumentCount"] == 2
    assert data["InstrumentList"] == [
        {"ExchangeSegment": "NSE_EQ", "SecurityId": "1333"},
        {"ExchangeSegment": "IDX_I", "SecurityId": "13"},
    ]


def test_encode_subscription_packet_backward_compatibility():
    instruments = [("NSE_FNO", 44608)]
    payload_str = encode_subscription_packet(instruments, mode=4)
    data = json.loads(payload_str)
    assert data["RequestCode"] == 17
    assert data["InstrumentCount"] == 1
    assert data["InstrumentList"] == [
        {"ExchangeSegment": "NSE_FNO", "SecurityId": "44608"}
    ]


def test_decode_ticker_packet_code_2_dhan_v2():
    # Official DhanHQ v2 16-byte Ticker packet:
    # Header (8 bytes): Code 2 (uint8), Len 16 (int16), Seg 1 (uint8), SecId 1333 (int32)
    # Payload (8 bytes): LTP 123.45 (float32), LTT 1791630000 (int32)
    raw = struct.pack("<BhBifi", 2, 16, 1, 1333, 123.45, 1791630000)
    assert len(raw) == 16

    parsed = decode_packet(raw)
    assert parsed is not None
    assert parsed["response_code"] == 2
    assert parsed["exchange_segment"] == 1
    assert parsed["security_id"] == 1333
    assert pytest.approx(parsed["ltp"], 0.01) == 123.45
    assert parsed["ltt"] == 1791630000


def test_decode_quote_packet_code_4_dhan_v2():
    # Official DhanHQ v2 50-byte Quote packet:
    # Header (8 bytes): Code 4 (uint8), Len 50 (int16), Seg 2 (uint8), SecId 44608 (int32)
    # Payload (42 bytes): LTP 160.5, LTQ 100, LTT 1728500000, VWAP 158.0, Vol 250000,
    # SellQty 5000, BuyQty 6000, Open 150.0, Close 152.0, High 165.0, Low 148.0
    raw = struct.pack(
        "<BhBifhifiiiffff",
        4, 50, 2, 44608,
        160.5, 100, 1728500000, 158.0, 250000,
        5000, 6000, 150.0, 152.0, 165.0, 148.0
    )
    assert len(raw) == 50

    parsed = decode_packet(raw)
    assert parsed is not None
    assert parsed["response_code"] == 4
    assert parsed["exchange_segment"] == 2
    assert parsed["security_id"] == 44608
    assert pytest.approx(parsed["ltp"], 0.01) == 160.5
    assert parsed["ltq"] == 100
    assert parsed["ltt"] == 1728500000
    assert pytest.approx(parsed["vwap"], 0.01) == 158.0
    assert parsed["volume"] == 250000
    assert parsed["total_sell_qty"] == 5000
    assert parsed["total_buy_qty"] == 6000
    assert parsed["open"] == 150.0
    assert parsed["close"] == 152.0
    assert parsed["high"] == 165.0
    assert parsed["low"] == 148.0


def test_decode_index_packet_code_1():
    # 32-byte Index packet: Code 1, Len 32, Seg 0 (IDX_I), SecId 13 (NIFTY 50)
    raw = struct.pack("<BhBifffffi", 1, 32, 0, 13, 22535.5, 22400.0, 22500.0, 22600.0, 22350.0, 1728500000)
    assert len(raw) == 32
    parsed = decode_packet(raw)
    assert parsed is not None
    assert parsed["response_code"] == 1
    assert parsed["exchange_segment"] == 0
    assert parsed["security_id"] == 13
    assert pytest.approx(parsed["ltp"], 0.01) == 22535.5
    assert parsed["open"] == 22400.0
    assert parsed["close"] == 22500.0
    assert parsed["high"] == 22600.0
    assert parsed["low"] == 22350.0
    assert parsed["ltt"] == 1728500000


def test_decode_login_ack_code_11():
    ack = b"\x0b\x00\x53\x00"
    parsed = decode_packet(ack)
    assert parsed is not None
    assert parsed["response_code"] == 11


def test_decode_truncated_packets():
    assert decode_packet(b"") is None
    assert decode_packet(b"\x02\x00") is None
    # Truncated code 2 (< 16 bytes)
    assert decode_packet(struct.pack("<BhB", 2, 16, 1)) is None
    # Truncated code 4 (< 50 bytes)
    assert decode_packet(struct.pack("<BhBii", 4, 50, 2, 44608, 1728500000)) is None


def test_decode_unknown_and_invalid():
    assert decode_packet(struct.pack("<BhBifi", 99, 16, 1, 1330, 25050.25, 1728500000)) is None
    assert decode_packet(None) is None
    assert decode_packet("string") is None
