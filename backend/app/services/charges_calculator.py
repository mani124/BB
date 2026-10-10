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
    - STT (Securities Transaction Tax): 0.1% (0.0010) on Sell Turnover only.
    - NSE Exchange Fee: 0.05% (0.0005) on Total Turnover.
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

    # NSE Exchange Fee: 0.05% (0.0005) on Total Turnover
    exchange_fee = round(total_turnover * 0.0005, 2)

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
