"""
Dhan HQ v2 Binary Packet Serialization and Deserialization Engine.

Provides binary packet encoding and decoding for the Dhan WebSocket feed
(wss://api-feed.dhan.co), supporting:
  - Login Request (Code 11)
  - Subscription Request (Code 15)
  - Ticker Response (Code 2, 16 bytes)
  - Quote Response (Code 4, 50 bytes)
  - Safe error handling for truncated and malformed frames
"""

import struct
from typing import Any, Optional


def encode_login_packet(client_id: str, access_token: str) -> bytes:
    """
    Encode Login Request (Code 11).

    Produces an 83-byte binary packet:
      - 2 bytes (uint16): Feed Request Code (11)
      - 2 bytes (uint16): Message Length (83)
      - 30 bytes: Client ID (null-padded / truncated)
      - 49 bytes: Access Token (null-padded / truncated)
    """
    header = struct.pack("<HH", 11, 83)
    cid_bytes = str(client_id).encode("utf-8")[:30].ljust(30, b"\x00")
    token_bytes = str(access_token).encode("utf-8")[:49].ljust(49, b"\x00")
    return header + cid_bytes + token_bytes


def encode_subscription_packet(
    instruments: list[tuple[int, int]], mode: int = 2
) -> bytes:
    """
    Encode Subscribe Request (Code 15).

    Header:
      - 2 bytes (uint16): Feed Request Code (15)
      - 2 bytes (uint16): Message Length
      - 2 bytes (uint16): Instrument Count
      - 2 bytes (uint16): Subscription Mode (e.g., 2 for Ticker, 4 for Quote)

    Body:
      - For each instrument (exchange_segment, security_id):
        - 1 byte (uint8): Exchange Segment
        - 4 bytes (int32): Security ID
    """
    body = bytearray()
    for seg, sec_id in instruments:
        body.extend(struct.pack("<Bi", int(seg), int(sec_id)))

    total_len = 8 + len(body)
    header = struct.pack("<HHHH", 15, total_len, len(instruments), int(mode))
    return bytes(header + body)


def decode_packet(raw_bytes: bytes) -> Optional[dict[str, Any]]:
    """
    Decode a binary frame received from the Dhan WebSocket feed into a dictionary.

    Supports:
      - Code 2: 16-byte Ticker packet (response_code, security_id, ltp, ltt)
      - Code 4: 50-byte Quote packet (response_code, security_id, ltp, vwap, volume,
                ltt, open, high, low, close)
      - Code 11: Login Acknowledgment
      - Code 50: Disconnection notice

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

        # Code 2: 16-byte Ticker packet
        if response_code == 2:
            if len(raw_bytes) < 16:
                return None
            code, seg, msg_len, sec_id, ltt, ltp = struct.unpack_from("<BBHiif", raw_bytes, 0)
            return {
                "response_code": 2,
                "exchange_segment": seg,
                "security_id": sec_id,
                "ltp": float(ltp),
                "ltt": int(ltt),
            }

        # Code 4: 50-byte Quote packet
        if response_code == 4:
            if len(raw_bytes) < 40:
                return None
            code, seg, msg_len, sec_id, ltt, ltp, ltq, vwap, volume, o, h, l = struct.unpack_from(
                "<BBHiififiiii", raw_bytes, 0
            )

            close_val: Optional[float] = None
            if len(raw_bytes) >= 44:
                try:
                    close_raw = struct.unpack_from("<i", raw_bytes, 40)[0]
                    close_val = float(close_raw)
                except Exception:
                    pass

            return {
                "response_code": 4,
                "exchange_segment": seg,
                "security_id": sec_id,
                "ltp": float(ltp),
                "ltq": int(ltq),
                "ltt": int(ltt),
                "vwap": float(vwap),
                "volume": int(volume),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": close_val,
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
