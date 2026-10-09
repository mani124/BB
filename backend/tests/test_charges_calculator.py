import pytest
from app.services.charges_calculator import calculate_option_trade_charges, TradeChargesBreakdown

def test_standard_round_trip_trade_charges():
    # Buy @ 100, Sell @ 150, Qty 65 (Nifty lot), 2 orders (1 Buy, 1 Sell)
    breakdown = calculate_option_trade_charges(buy_price=100.0, sell_price=150.0, quantity=65, orders_count=2)
    assert isinstance(breakdown, TradeChargesBreakdown)
    assert breakdown.buy_turnover == 6500.0
    assert breakdown.sell_turnover == 9750.0
    assert breakdown.total_turnover == 16250.0
    assert breakdown.orders_count == 2
    assert breakdown.brokerage == 40.0
    # STT = 9750 * 0.0010 = 9.75
    assert breakdown.stt == 9.75
    # Exchange Fee = 16250 * 0.0005 = 8.125 -> round 8.13 or 8.12
    assert abs(breakdown.exchange_fee - 8.13) <= 0.02
    # SEBI Fee = 16250 * 0.000001 = 0.016 -> 0.02
    assert abs(breakdown.sebi_fee - 0.02) <= 0.01
    # Stamp Duty = 6500 * 0.00003 = 0.195 -> 0.20
    assert abs(breakdown.stamp_duty - 0.20) <= 0.02
    # GST = (40 + 8.13 + 0.02) * 0.18 = 8.67
    assert abs(breakdown.gst - 8.67) <= 0.03
    expected_total = round(breakdown.brokerage + breakdown.stt + breakdown.exchange_fee + breakdown.sebi_fee + breakdown.stamp_duty + breakdown.gst, 2)
    assert breakdown.total_charges == expected_total

def test_partial_profit_booking_three_orders():
    # 3 orders (1 Buy, 2 Sells)
    breakdown = calculate_option_trade_charges(buy_price=200.0, sell_price=260.0, quantity=130, orders_count=3)
    assert breakdown.brokerage == 60.0
    assert breakdown.orders_count == 3
    assert breakdown.total_charges > 60.0

def test_zero_quantity_or_invalid_price():
    # Review Focus: Zero quantity must yield zeroed breakdown without division by zero
    breakdown = calculate_option_trade_charges(buy_price=0.0, sell_price=0.0, quantity=0, orders_count=2)
    assert breakdown.total_turnover == 0.0
    assert breakdown.brokerage == 0.0
    assert breakdown.total_charges == 0.0

def test_negative_price_or_quantity():
    # Negative prices or negative quantity must also safely yield zeroed breakdown
    breakdown = calculate_option_trade_charges(buy_price=-10.0, sell_price=50.0, quantity=65, orders_count=2)
    assert breakdown.total_turnover == 0.0
    assert breakdown.brokerage == 0.0
    assert breakdown.total_charges == 0.0

    breakdown_qty = calculate_option_trade_charges(buy_price=100.0, sell_price=150.0, quantity=-65, orders_count=2)
    assert breakdown_qty.total_turnover == 0.0
    assert breakdown_qty.brokerage == 0.0
    assert breakdown_qty.total_charges == 0.0

def test_option_expired_worthless_zero_sell():
    # Option expires worthless at sell_price=0.0 with positive buy_price and quantity
    breakdown = calculate_option_trade_charges(buy_price=50.0, sell_price=0.0, quantity=65, orders_count=2)
    assert breakdown.buy_turnover == 3250.0
    assert breakdown.sell_turnover == 0.0
    assert breakdown.total_turnover == 3250.0
    assert breakdown.brokerage == 40.0
    assert breakdown.stt == 0.0  # STT is only on sell turnover
    assert breakdown.stamp_duty == round(3250.0 * 0.00003, 2)
    assert breakdown.total_charges > 40.0
