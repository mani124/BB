"""Broker-neutral types for live order routing.

The order router (``order_router.py``) talks only to a ``BrokerAdapter``. Definedge Securities is the first
adapter (``broker_definedge.py``); another broker is one more class with the same methods.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# Normalised order states. Adapters map the broker's own words onto these.
NEW, OPEN, COMPLETE, CANCELED, REJECTED, UNKNOWN = "NEW", "OPEN", "COMPLETE", "CANCELED", "REJECTED", "UNKNOWN"
ACTIVE_STATES = (NEW, OPEN)
FINAL_STATES = (COMPLETE, CANCELED, REJECTED)


class BrokerError(Exception):
    """Any broker failure. The router never retries blindly; subclasses say what is known about the order."""


class BrokerNotSent(BrokerError):
    """The request never reached the broker (connection refused, bad local input). Safe to release the tag."""


class BrokerRejected(BrokerError):
    """The broker answered and refused the order. Definite: nothing is working at the broker."""


class BrokerTimeout(BrokerError):
    """No usable answer. The order may or may not be at the broker: state is UNKNOWN until looked up."""


class BrokerAuthExpired(BrokerError):
    """The session key is missing or expired. Needs a fresh login before any order can go."""


@dataclass(frozen=True)
class Contract:
    exchange: str  # broker's exchange code, e.g. NFO / BFO
    trading_symbol: str
    lot_size: int
    tick_size: float = 0.05


@dataclass
class OrderRequest:
    tag: str  # our idempotency tag; also sent as the broker's remarks so the order can be found again
    contract: Contract
    side: str  # BUY | SELL
    quantity: int
    order_type: str  # MARKET | LIMIT
    price: float  # 0 for MARKET
    product: str = "INTRADAY"
    validity: str = "DAY"
    algo_id: str = ""


@dataclass
class OrderResult:
    broker_order_id: str = ""
    status: str = UNKNOWN
    filled_qty: int = 0
    avg_price: float = 0.0
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class BrokerAdapter(Protocol):
    name: str

    def has_session(self) -> bool: ...

    async def verify_session(self) -> None:
        """Raise BrokerAuthExpired when the session is not usable."""

    async def resolve_contract(self, *, underlying: str, expiry: str, strike: float, option_type: str,
                               segment: str) -> Contract:
        """Raise BrokerError when the contract cannot be identified unambiguously."""

    async def place_order(self, req: OrderRequest) -> OrderResult: ...

    async def get_order(self, broker_order_id: str) -> OrderResult: ...

    async def find_order_by_tag(self, tag: str) -> Optional[OrderResult]: ...

    async def cancel_order(self, broker_order_id: str) -> None: ...

    async def net_positions(self) -> dict[str, int]:
        """trading_symbol -> net open quantity (long positive)."""
