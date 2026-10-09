import pytest
import struct
from app.services.dhan_packet_codec import (
    encode_login_packet,
    encode_subscription_packet,
    decode_packet
)

def test_encode_login_packet():
    packet = encode_login_packet("1000000000", "my_sample_access_token")
    assert len(packet) == 83
    req_code, msg_len = struct.unpack_from("<HH", packet, 0)
    assert req_code == 11
    assert msg_len == 83


def test_encode_subscription_packet():
    instruments = [(1, 1330), (2, 44608)]
    packet = encode_subscription_packet(instruments, mode=2)
    assert len(packet) == 18
    req_code, msg_len, count, mode = struct.unpack_from("<HHHH", packet, 0)
    assert req_code == 15
    assert msg_len == 18
    assert count == 2
    assert mode == 2

    seg1, sec1 = struct.unpack_from("<Bi", packet, 8)
    assert seg1 == 1
    assert sec1 == 1330

    seg2, sec2 = struct.unpack_from("<Bi", packet, 13)
    assert seg2 == 2
    assert sec2 == 44608


def test_decode_ticker_packet_code_2():
    # 16-byte Ticker packet: Code 2, Len 16, Seg 1, SecId 1330, LTP 25050.25, LTT 1728500000
    dummy = struct.pack("<BBHiif", 2, 0, 16, 1330, 1728500000, 25050.25)
    parsed = decode_packet(dummy)
    assert parsed is not None
    assert parsed["response_code"] == 2
    assert parsed["security_id"] == 1330
    assert pytest.approx(parsed["ltp"], 0.01) == 25050.25
    assert parsed["ltt"] == 1728500000


def test_decode_quote_packet_code_4():
    # 50-byte Quote packet: Code 4, Len 50, Seg 2, SecId 44608, LTP 160.5, VWAP 158.0, Vol 250000
    dummy = struct.pack("<BBHiififiiii", 4, 0, 50, 44608, 1728500000, 160.5, 100, 158.0, 250000, 150, 165, 148)
    parsed = decode_packet(dummy)
    assert parsed is not None
    assert parsed["response_code"] == 4
    assert parsed["security_id"] == 44608
    assert pytest.approx(parsed["ltp"], 0.01) == 160.5
    assert pytest.approx(parsed["vwap"], 0.01) == 158.0
    assert parsed["volume"] == 250000
    assert parsed["open"] == 150.0
    assert parsed["high"] == 165.0
    assert parsed["low"] == 148.0


def test_decode_login_ack_code_11():
    ack = b"\x0b\x00\x53\x00"
    parsed = decode_packet(ack)
    assert parsed is not None
    assert parsed["response_code"] == 11


def test_decode_truncated_packets():
    assert decode_packet(b"") is None
    assert decode_packet(b"\x02\x00") is None
    # Truncated code 2
    assert decode_packet(struct.pack("<BBH", 2, 0, 16)) is None
    # Truncated code 4
    assert decode_packet(struct.pack("<BBHii", 4, 0, 50, 44608, 1728500000)) is None


def test_decode_unknown_and_invalid():
    # Unknown response code 99
    assert decode_packet(struct.pack("<BBHiif", 99, 0, 16, 1330, 1728500000, 25050.25)) is None
    # Non-bytes input
    assert decode_packet(None) is None
    assert decode_packet("string") is None
