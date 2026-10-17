"""
Dhan HQ v2 Market Feed Packet Serialization and Deserialization Engine.

Provides wire protocol encoding and binary packet decoding conforming to the
official DhanHQ v2 Live Market Feed specification:
https://dhanhq.co/docs/v2/live-market-feed/

Features:
  - Wire Subscription: JSON requests (RequestCode 15 for Ticker, 17 for Quote)
  - 8-Byte Binary Response Header:
      Byte 0: Response Code (uint8)
      Bytes 1-2: Message Length (int16)
      Byte 3: Exchange Segment (uint8)
      Bytes 4-7: Security ID (int32)
  - Response Code 1: Index Packet (32 bytes)
  - Response Code 2: Ticker Packet (16 bytes, LTP + LTT)
  - Response Code 4: Quote Packet (50 bytes, LTP + LTQ + LTT + VWAP + Volume + OHLC)
  - Response Code 6: Prev Close Packet (16 bytes)
  - Response Code 50: Disconnection alert (10 bytes)
  - Safe error handling for truncated, malformed, or unrecognized frames
"""

import json
import struct
from typing import Any, Optional, Union

SEGMENT_INT_TO_STR: dict[int, str] = {
    0: "IDX_I",
    1: "NSE_EQ",
    2: "NSE_FNO",
    3: "NSE_CURRENCY",
    4: "BSE_EQ",
    5: "MCX_COMM",
    7: "BSE_CURRENCY",
    8: "BSE_FNO",
}

SEGMENT_STR_TO_INT: dict[str, int] = {
    "IDX_I": 0,
    "NSE_EQ": 1,
    "NSE_FNO": 2,
    "NSE_CURRENCY": 3,
    "BSE_EQ": 4,
    "MCX_COMM": 5,
    "BSE_CURRENCY": 7,
    "BSE_FNO": 8,
}


def segment_to_str(segment: Union[int, str]) -> str:
    """Convert integer or string segment representation to standard Dhan segment string."""
    if isinstance(segment, int):
        return SEGMENT_INT_TO_STR.get(segment, "NSE_EQ")
    seg_upper = str(segment).upper()
    if seg_upper in SEGMENT_STR_TO_INT:
        return seg_upper
    try:
        seg_int = int(segment)
        return SEGMENT_INT_TO_STR.get(seg_int, "NSE_EQ")
    except (ValueError, TypeError):
        return "NSE_EQ"


def segment_to_int(segment: Union[int, str]) -> int:
    """Convert integer or string segment representation to standard Dhan segment int."""
    if isinstance(segment, int):
        return segment
    seg_upper = str(segment).upper()
    if seg_upper in SEGMENT_STR_TO_INT:
        return SEGMENT_STR_TO_INT[seg_upper]
    try:
        return int(segment)
    except (ValueError, TypeError):
        return 1


def encode_subscription_json(
    instruments: list[tuple[Union[int, str], Union[int, str]]],
    request_code: int = 15
) -> str:
    """
    Encode a subscription request into a DhanHQ v2 compliant JSON string.
    
    Format:
    {
        "RequestCode": 15,
        "InstrumentCount": len,
        "InstrumentList": [
            {"ExchangeSegment": "NSE_EQ", "SecurityId": "1333"}, ...
        ]
    }
    """
    instrument_list = [
        {
            "ExchangeSegment": segment_to_str(seg),
            "SecurityId": str(sec_id),
        }
        for seg, sec_id in instruments
    ]
    payload = {
        "RequestCode": int(request_code),
        "InstrumentCount": len(instrument_list),
        "InstrumentList": instrument_list,
    }
    return json.dumps(payload)


def encode_subscription_packet(
    instruments: list[tuple[Union[int, str], Union[int, str]]],
    mode: int = 2
) -> str:
    """
    Backward-compatible subscription encoder returning the Dhan v2 JSON string.
    Mode 2 maps to RequestCode 15 (Ticker), Mode 4 maps to RequestCode 17 (Quote).
    """
    req_code = 17 if mode == 4 else 15
    return encode_subscription_json(instruments, request_code=req_code)


def encode_login_packet(client_id: str, access_token: str) -> bytes:
    """
    Legacy binary login packet (Code 11).
    Note: Dhan v2 authenticates via WebSocket connection URL parameters,
    so this is preserved only for backward compatibility with legacy tests.
    """
    header = struct.pack("<HH", 11, 83)
    cid_bytes = str(client_id).encode("utf-8")[:30].ljust(30, b"\x00")
    token_bytes = str(access_token).encode("utf-8")[:49].ljust(49, b"\x00")
    return header + cid_bytes + token_bytes


def decode_packet(raw_bytes: bytes) -> Optional[dict[str, Any]]:
    """
    Decode a binary frame received from the Dhan WebSocket feed into a dictionary.

    Conforms to official DhanHQ v2 layout:
      - 8-byte Response Header:
          Byte 0: Response Code (uint8)
          Bytes 1-2: Message Length (int16)
          Byte 3: Exchange Segment (uint8)
          Bytes 4-7: Security ID (int32)
      - Code 1: 32-byte Index packet (LTP, Open, Close, High, Low, LTT)
      - Code 2: 16-byte Ticker packet (LTP, LTT)
      - Code 4: 50-byte Quote packet (LTP, LTQ, LTT, VWAP, Volume, SellQty, BuyQty, Open, Close, High, Low)
      - Code 6: 16-byte Prev Close packet (PrevClose, PrevOI)
      - Code 11: Login Acknowledgment
      - Code 50: Disconnection notice (ReasonCode)

    Returns None for truncated, malformed, or unrecognized frames without
    raising unhandled exceptions.
    """
    if not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
        return None

    if len(raw_bytes) < 4:
        return None

    try:
        response_code = raw_bytes[0]

        # Code 11: Login Acknowledgement
        if response_code == 11:
            return {"response_code": 11}

        # Code 1: 32-byte Index packet
        if response_code == 1:
            if len(raw_bytes) < 32:
                return None
            code, msg_len, seg, sec_id, ltp, o, c, h, l, ltt = struct.unpack_from(
                "<BhBifffffi", raw_bytes, 0
            )
            return {
                "response_code": 1,
                "exchange_segment": seg,
                "security_id": sec_id,
                "ltp": float(ltp),
                "open": float(o),
                "close": float(c),
                "high": float(h),
                "low": float(l),
                "ltt": int(ltt),
            }

        # Code 2: 16-byte Ticker packet
        # Bytes 0-7: Header (<BhBi: code=2, msg_len=16, seg, sec_id)
        # Bytes 8-11: float32 ltp
        # Bytes 12-15: int32 ltt
        if response_code == 2:
            if len(raw_bytes) < 16:
                return None
            code, msg_len, seg, sec_id, ltp, ltt = struct.unpack_from(
                "<BhBifi", raw_bytes, 0
            )
            return {
                "response_code": 2,
                "exchange_segment": seg,
                "security_id": sec_id,
                "ltp": float(ltp),
                "ltt": int(ltt),
            }

        # Code 4: 50-byte Quote packet
        # Bytes 0-7: Header (<BhBi: code=4, msg_len=50, seg, sec_id)
        # Bytes 8-11: float32 ltp
        # Bytes 12-13: int16 ltq
        # Bytes 14-17: int32 ltt
        # Bytes 18-21: float32 vwap (Average Trade Price)
        # Bytes 22-25: int32 volume
        # Bytes 26-29: int32 total_sell_qty
        # Bytes 30-33: int32 total_buy_qty
        # Bytes 34-37: float32 open
        # Bytes 38-41: float32 close
        # Bytes 42-45: float32 high
        # Bytes 46-49: float32 low
        if response_code == 4:
            if len(raw_bytes) < 50:
                return None
            code, msg_len, seg, sec_id, ltp, ltq, ltt, vwap, vol, sell_q, buy_q, o, c, h, l = struct.unpack_from(
                "<BhBifhifiiiffff", raw_bytes, 0
            )
            return {
                "response_code": 4,
                "exchange_segment": seg,
                "security_id": sec_id,
                "ltp": float(ltp),
                "ltq": int(ltq),
                "ltt": int(ltt),
                "vwap": float(vwap),
                "volume": int(vol),
                "total_sell_qty": int(sell_q),
                "total_buy_qty": int(buy_q),
                "open": float(o),
                "close": float(c),
                "high": float(h),
                "low": float(l),
            }

        # Code 6: 16-byte Prev Close packet
        if response_code == 6:
            if len(raw_bytes) < 16:
                return None
            code, msg_len, seg, sec_id, prev_close, prev_oi = struct.unpack_from(
                "<BhBifi", raw_bytes, 0
            )
            return {
                "response_code": 6,
                "exchange_segment": seg,
                "security_id": sec_id,
                "prev_close": float(prev_close),
                "prev_oi": int(prev_oi),
            }

        # Code 50: Disconnection alert
        if response_code == 50:
            reason = None
            if len(raw_bytes) >= 10:
                reason = struct.unpack_from("<h", raw_bytes, 8)[0]
            return {"response_code": 50, "reason_code": reason}

        # Unrecognized packet type
        return None

    except Exception:
        return None
