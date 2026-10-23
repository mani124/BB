"""
Regulatory Charges and Brokerage Calculator for Indian NSE Option Contracts.
Implements official Dhan HQ / SEBI / NSE F&O fee and tax schedule (revised post-SEBI October 2024 directives).
"""

from pydantic import BaseModel


class TradeChargesBreakdown(BaseModel):
    buy_turnover: float = 0.0
    sell_turnover: float = 0.0
    total_turnover: float = 0.0
    orders_count: int = 0
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_fee: float = 0.0
    sebi_fee: float = 0.0
    stamp_duty: float = 0.0
    gst: float = 0.0
    total_charges: float = 0.0


def calculate_option_trade_charges(
    buy_price: float,
    sell_price: float,
    quantity: int,
    orders_count: int = 2,
    brokerage_per_order: float = 20.0,
) -> TradeChargesBreakdown:
    """
    Calculate statutory charges and brokerage for Indian NSE Option contracts.

    Fee Schedule:
    - Brokerage: Flat ₹20 per executed order leg (configurable via brokerage_per_order).
    - STT (Securities Transaction Tax): 0.15% (0.0015) on Sell Turnover only (from 1 April 2026).
    - NSE Exchange Fee: 0.03553% (0.0003553) on Total Turnover.
    - SEBI Turnover Fee: ₹10 per crore (0.000001) on Total Turnover.
    - Stamp Duty: 0.003% (0.00003) on Buy Turnover only.
    - GST: 18% on (Brokerage + Exchange Fee + SEBI Fee).
    - Total Charges: Sum of all charges above.

    Zero or invalid inputs (quantity <= 0 or invalid prices) yield a zeroed breakdown.
    """
    if quantity <= 0 or buy_price < 0 or sell_price < 0 or (buy_price <= 0 and sell_price <= 0):
        return TradeChargesBreakdown(
            buy_turnover=0.0,
            sell_turnover=0.0,
            total_turnover=0.0,
            orders_count=0,
            brokerage=0.0,
            stt=0.0,
            exchange_fee=0.0,
            sebi_fee=0.0,
            stamp_duty=0.0,
            gst=0.0,
            total_charges=0.0,
        )

    buy_turnover = round(buy_price * quantity, 2)
    sell_turnover = round(sell_price * quantity, 2)
    total_turnover = round(buy_turnover + sell_turnover, 2)

    effective_orders = max(0, orders_count)
    safe_brokerage_rate = max(0.0, float(brokerage_per_order))
    brokerage = round(effective_orders * safe_brokerage_rate, 2)

    # STT: 0.15% (0.0015) on Sell Turnover only (effective 1 April 2026)
    stt = round(sell_turnover * 0.0015, 2)

    # NSE Exchange Transaction Fee: ₹3,552.99/crore (~0.03553% inclusive of IPFT per NSE circular FA73061)
    NSE_OPTION_EXCHANGE_TXN_RATE = 0.0003553
    exchange_fee = round(total_turnover * NSE_OPTION_EXCHANGE_TXN_RATE, 2)

    # SEBI Turnover Fee: ₹10 per crore (0.000001) on Total Turnover
    sebi_fee = round(total_turnover * 0.000001, 2)

    # Stamp Duty: 0.003% (0.00003) on Buy Turnover only
    stamp_duty = round(buy_turnover * 0.00003, 2)

    # GST: 18% on (Brokerage + Exchange Fee + SEBI Fee)
    gst = round((brokerage + exchange_fee + sebi_fee) * 0.18, 2)

    # Total Charges
    total_charges = round(brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst, 2)

    return TradeChargesBreakdown(
        buy_turnover=buy_turnover,
        sell_turnover=sell_turnover,
        total_turnover=total_turnover,
        orders_count=effective_orders,
        brokerage=brokerage,
        stt=stt,
        exchange_fee=exchange_fee,
        sebi_fee=sebi_fee,
        stamp_duty=stamp_duty,
        gst=gst,
        total_charges=total_charges,
    )


def calculate_equity_delivery_charges(
    buy_price: float,
    sell_price: float,
    quantity: int,
    brokerage_per_order: float = 0.0,
    dp_charge: float = 15.34,
) -> TradeChargesBreakdown:
    """
    Statutory charges for an NSE cash-segment delivery (CNC) round trip, used by the swing book.

    Fee schedule (Zerodha's published delivery schedule, 2026; the statutory parts are broker independent):
    - Brokerage: ``brokerage_per_order`` per leg (0 by default: delivery is free at the discount brokers; confirm the
      Dhan schedule before relying on this).
    - STT: 0.1% on both the buy and the sell turnover.
    - NSE transaction fee: 0.00307% of total turnover. SEBI fee: Rs 10 per crore of total turnover.
    - Stamp duty: 0.015% on the buy turnover.
    - GST: 18% on (brokerage + exchange fee + SEBI fee).
    - DP charge: ``dp_charge`` once on the sell day (already includes GST, so it is not taxed again).
    Zero or invalid inputs yield a zeroed breakdown. ``stt`` carries both legs.
    """
    if quantity <= 0 or buy_price <= 0 or sell_price <= 0:
        return TradeChargesBreakdown()
    buy_turnover = round(buy_price * quantity, 2)
    sell_turnover = round(sell_price * quantity, 2)
    total_turnover = round(buy_turnover + sell_turnover, 2)
    brokerage = round(2 * max(0.0, float(brokerage_per_order)), 2)
    stt = round(total_turnover * 0.001, 2)
    exchange_fee = round(total_turnover * 0.0000307, 2)
    sebi_fee = round(total_turnover * 0.000001, 2)
    stamp_duty = round(buy_turnover * 0.00015, 2)
    gst = round((brokerage + exchange_fee + sebi_fee) * 0.18, 2)
    dp = round(max(0.0, float(dp_charge)), 2)
    total = round(brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst + dp, 2)
    return TradeChargesBreakdown(
        buy_turnover=buy_turnover, sell_turnover=sell_turnover, total_turnover=total_turnover, orders_count=2,
        brokerage=brokerage, stt=stt, exchange_fee=exchange_fee, sebi_fee=sebi_fee, stamp_duty=stamp_duty, gst=gst,
        total_charges=total,
    )
