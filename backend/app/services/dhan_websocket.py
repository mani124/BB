"""
Dhan HQ v2 Real-Time WebSocket Manager.

Maintains a persistent binary WebSocket connection to wss://api-feed.dhan.co,
providing:
  - Binary login authentication handshake (Code 11)
  - Dynamic instrument subscription (Code 15) with 100-scrip packet batching
  - Fast reader loop decoding 16-byte Ticker and 50-byte Quote frames
  - Asynchronous tick dispatch to callbacks
  - Resilient exponential backoff auto-reconnection and instrument re-subscription
  - Periodic keepalive ping frames
  - Zero-Token Persistence: tokens and credentials stored only in memory
"""

import asyncio
import inspect
import json
import logging
import urllib.parse
from typing import Any, Awaitable, Callable, Optional, Set, Tuple

import websockets

from app.services.dhan_packet_codec import (
    decode_packet,
    encode_subscription_json,
    encode_subscription_packet,
)

logger = logging.getLogger(__name__)


class DhanWebSocketManager:
    """
    Manages persistent binary streaming connection to Dhan WebSocket feed.
    """

    def __init__(
        self,
        on_tick_callback: Optional[Callable[[dict[str, Any]], Any]] = None,
        url: str = "wss://api-feed.dhan.co",
        ping_interval: float = 15.0,
        backoff_delays: Tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0),
    ) -> None:
        self.on_tick_callback = on_tick_callback
        self.url = url
        self.ping_interval = ping_interval
        self.backoff_delays = backoff_delays

        self.status: str = "DISCONNECTED"  # DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING
        self._ws: Any = None
        self._client_id: Optional[str] = None
        self._access_token: Optional[str] = None
        self._subscribed_instruments: Set[Tuple[int, int]] = set()

        self._reader_task: Optional[asyncio.Task[None]] = None
        self._ping_task: Optional[asyncio.Task[None]] = None
        self._reconnect_task: Optional[asyncio.Task[None]] = None
        self._intentional_disconnect: bool = False
        self._reconnect_count: int = 0
        self._last_tick_time: Optional[float] = None
        self._ticks_count: int = 0

    @property
    def is_connected(self) -> bool:
        """True if the connection is active and status is CONNECTED."""
        return self.status == "CONNECTED" and self._ws is not None

    @property
    def is_healthy(self) -> bool:
        """
        True only if connected AND fresh market data ticks or responses have
        been received recently (within 30s), proving that subscriptions are active.
        """
        if not self.is_connected or self._last_tick_time is None:
            return False
        try:
            now = asyncio.get_running_loop().time()
            return (now - self._last_tick_time) <= 30.0
        except RuntimeError:
            return False

    @property
    def last_tick_time(self) -> Optional[float]:
        return self._last_tick_time

    @property
    def subscribed_instruments(self) -> Set[Tuple[int, int]]:
        """Set of currently subscribed (exchange_segment, security_id) tuples."""
        return set(self._subscribed_instruments)

    def _build_ws_url(self) -> str:
        """
        Build WebSocket URL with Dhan v2 authentication query parameters.
        Format: wss://api-feed.dhan.co?version=2&token={access_token}&clientId={client_id}&authType=2
        """
        url = self.url
        if "version=" not in url and "token=" not in url and self._access_token:
            separator = "&" if "?" in url else "?"
            params = {
                "version": "2",
                "token": self._access_token,
                "clientId": self._client_id,
                "authType": "2",
            }
            url = f"{url}{separator}{urllib.parse.urlencode(params)}"
        return url

    async def connect(self, client_id: str, access_token: str) -> None:
        """
        Connect to Dhan WebSocket feed via v2 authenticated URL parameters.
        """
        if self.status != "DISCONNECTED" or (self._reconnect_task and not self._reconnect_task.done()):
            logger.warning("WebSocket manager already active or reconnecting; disconnecting first.")
            await self.disconnect()

        self._client_id = str(client_id)
        self._access_token = str(access_token)
        self._intentional_disconnect = False
        self.status = "CONNECTING"

        try:
            conn_result = websockets.connect(self._build_ws_url(), ping_interval=None)
            if inspect.isawaitable(conn_result):
                self._ws = await conn_result
            else:
                self._ws = conn_result

            self.status = "CONNECTED"
            masked_id = f"{self._client_id[:3]}***" if len(self._client_id) >= 3 else "***"
            logger.info("Connected to Dhan WebSocket for client %s", masked_id)

            # Launch background streaming loops
            self._reader_task = asyncio.create_task(self._reader_loop())
            self._ping_task = asyncio.create_task(self._ping_loop())

            # Re-subscribe existing instruments if any (e.g., reconnect)
            if self._subscribed_instruments:
                await self._send_subscriptions(list(self._subscribed_instruments), mode=2)

        except Exception as exc:
            self.status = "DISCONNECTED"
            self._ws = None
            logger.error("Failed to connect to Dhan WebSocket: %s", type(exc).__name__)
            raise

    async def subscribe(
        self, instruments: list[Tuple[int, int]], mode: int = 2
    ) -> None:
        """
        Subscribe to market feed updates for the specified instruments.
        Instruments are chunked in batches of <= 100 to respect Dhan limits.
        """
        if not instruments:
            return

        for item in instruments:
            self._subscribed_instruments.add(item)

        if self.is_connected and self._ws is not None:
            await self._send_subscriptions(instruments, mode=mode)

    async def unsubscribe(
        self, instruments: list[Tuple[int, int]]
    ) -> None:
        """
        Remove instruments from subscription registry.
        """
        for item in instruments:
            self._subscribed_instruments.discard(item)

    async def _send_subscriptions(
        self, instruments: list[Tuple[int, int]], mode: int = 2
    ) -> None:
        """Send v2 JSON subscription frames in chunks of 100."""
        req_code = 17 if mode == 4 else 15
        for i in range(0, len(instruments), 100):
            chunk = instruments[i : i + 100]
            json_payload = encode_subscription_json(chunk, request_code=req_code)
            await self._ws.send(json_payload)

    async def disconnect(self) -> None:
        """
        Cleanly disconnect WebSocket, cancel background tasks, and reset state.
        """
        self._intentional_disconnect = True
        self.status = "DISCONNECTED"

        # Cancel reconnect task if active
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        self._reconnect_task = None

        # Cancel ping task
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        self._ping_task = None

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._reader_task = None

        # Close WebSocket connection
        if self._ws is not None:
            try:
                close_result = self._ws.close()
                if inspect.isawaitable(close_result):
                    await close_result
            except Exception:
                pass
            self._ws = None

        logger.info("Dhan WebSocket disconnected cleanly")

    async def _reader_loop(self) -> None:
        """Continuous binary packet reading and dispatch loop."""
        should_reconnect = False
        try:
            while not self._intentional_disconnect and self._ws is not None:
                msg = await self._ws.recv()
                if isinstance(msg, str):
                    try:
                        parsed_json = json.loads(msg)
                        if parsed_json.get("status") == "success" or parsed_json.get("RequestCode"):
                            try:
                                self._last_tick_time = asyncio.get_running_loop().time()
                            except RuntimeError:
                                pass
                    except Exception:
                        pass
                    continue

                packet = decode_packet(msg)
                if packet is None:
                    continue

                resp_code = packet.get("response_code")
                if resp_code in (1, 2, 4, 6):
                    try:
                        self._last_tick_time = asyncio.get_running_loop().time()
                    except RuntimeError:
                        pass
                    self._ticks_count += 1
                    if self.on_tick_callback is not None:
                        try:
                            cb_res = self.on_tick_callback(packet)
                            if inspect.isawaitable(cb_res):
                                await cb_res
                        except Exception as cb_err:
                            logger.error("Error executing tick callback: %s", cb_err)
                elif resp_code == 50:
                    logger.warning(
                        "Dhan WebSocket server disconnection notice: code=%s",
                        packet.get("reason_code"),
                    )
                    should_reconnect = True
                    break
                elif resp_code == 11:
                    logger.debug("Dhan WebSocket login acknowledged (Code 11)")

        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not self._intentional_disconnect:
                logger.warning(
                    "Dhan WebSocket reader interrupted: %s", type(exc).__name__
                )
                should_reconnect = True
        finally:
            if should_reconnect and not self._intentional_disconnect:
                self._schedule_reconnect()

    async def _ping_loop(self) -> None:
        """Periodic keepalive ping frame sender."""
        try:
            while not self._intentional_disconnect and self._ws is not None:
                await asyncio.sleep(self.ping_interval)
                if self._intentional_disconnect or self._ws is None:
                    break
                if hasattr(self._ws, "ping"):
                    try:
                        ping_res = self._ws.ping()
                        if inspect.isawaitable(ping_res):
                            await ping_res
                    except Exception as ping_err:
                        logger.debug("WebSocket keepalive ping error: %s", ping_err)
                        break
        except asyncio.CancelledError:
            return

    def _schedule_reconnect(self) -> None:
        """Schedule background reconnection if not already in progress."""
        if self._intentional_disconnect:
            return
        self.status = "RECONNECTING"
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Exponential backoff reconnection loop."""
        self.status = "RECONNECTING"
        delay_idx = 0

        while not self._intentional_disconnect:
            delay = (
                self.backoff_delays[delay_idx]
                if delay_idx < len(self.backoff_delays)
                else self.backoff_delays[-1]
            )
            delay_idx += 1
            logger.info("Attempting WebSocket reconnect in %ss...", delay)

            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

            if self._intentional_disconnect:
                break

            try:
                self._reconnect_count += 1
                if self._ws is not None:
                    try:
                        close_result = self._ws.close()
                        if inspect.isawaitable(close_result):
                            await close_result
                    except Exception:
                        pass
                    self._ws = None

                conn_result = websockets.connect(self._build_ws_url(), ping_interval=None)
                if inspect.isawaitable(conn_result):
                    self._ws = await conn_result
                else:
                    self._ws = conn_result

                self.status = "CONNECTED"

                # Re-subscribe all registered instruments
                if self._subscribed_instruments:
                    await self._send_subscriptions(
                        list(self._subscribed_instruments), mode=2
                    )

                self._reader_task = asyncio.create_task(self._reader_loop())
                self._ping_task = asyncio.create_task(self._ping_loop())
                logger.info(
                    "Dhan WebSocket reconnected successfully; %d instruments re-subscribed",
                    len(self._subscribed_instruments),
                )
                return
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Reconnection attempt failed: %s", type(exc).__name__)

        if not self._intentional_disconnect and self.status != "CONNECTED":
            self.status = "DISCONNECTED"

    def get_status(self) -> dict[str, Any]:
        """
        Return public status dictionary. Never contains secrets or tokens.
        """
        return {
            "status": self.status,
            "is_connected": self.is_connected,
            "subscribed_count": len(self._subscribed_instruments),
            "subscribed_instruments": list(self._subscribed_instruments),
            "url": self.url,
            "reconnect_count": self._reconnect_count,
            "feed_mode": "websocket_live" if self.is_connected else "disconnected",
        }

    def __repr__(self) -> str:
        return (
            f"<DhanWebSocketManager status={self.status} "
            f"is_connected={self.is_connected} "
            f"subscribed_count={len(self._subscribed_instruments)}>"
        )

    def __str__(self) -> str:
        return self.__repr__()
